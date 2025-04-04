import asyncio
import os
from contextlib import suppress
from loguru import logger
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.enums import ParseMode
import requests
from bs4 import BeautifulSoup
from random import choice
from group_chat import setup_all_handlers

# Инициализация окружения
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

class BotConfig:
    """Конфигурация бота и путей"""
    def __init__(self):
        # Используем относительные пути
        self.FILE_PATH = os.path.join('data', 'value.txt')
        self.USER_FILE_PATH = os.path.join('data', 'subscribed_users.txt')
        os.makedirs('data', exist_ok=True)
        
        # Настройки бота
        self.bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
        
        # Состояние приложения
        self.last_value = None
        self.subscribed_users = set()
        self.is_sending_values = False
        self.lock = asyncio.Lock()

class BotServices:
    """Сервисы бота для работы с данными"""
    def __init__(self, config: BotConfig):
        self.config = config
    
    async def load_subscribed_users(self):
        """Загрузка подписанных пользователей"""
        if os.path.exists(self.config.USER_FILE_PATH):
            async with self.config.lock:
                with open(self.config.USER_FILE_PATH, 'r') as file:
                    self.config.subscribed_users = {
                        int(line.strip()) for line in file if line.strip().isdigit()
                    }

    async def save_subscribed_user(self, user_id: int):
        """Сохранение подписчика"""
        async with self.config.lock:
            with open(self.config.USER_FILE_PATH, 'a') as file:
                file.write(f"{user_id}\n")
            logger.info(f"User {user_id} subscribed")

    async def read_value_from_file(self):
        """Чтение значения из файла"""
        try:
            with open(self.config.FILE_PATH, 'r') as file:
                if line := file.readline().strip():
                    if line.startswith("check = "):
                        return line.split('=')[1].strip()
        except Exception as e:
            logger.error(f"File read error: {e}")
        return None

async def setup_bot_handlers(dp: Dispatcher, config: BotConfig, services: BotServices):
    """Настройка обработчиков команд"""
    
    @dp.message(Command('start'))
    async def send_welcome(message: types.Message):
        user_id = message.from_user.id
        async with config.lock:
            if user_id not in config.subscribed_users:
                config.subscribed_users.add(user_id)
                await services.save_subscribed_user(user_id)
                response = "Вы подписались на рассылку значений."
            else:
                response = "Вы уже подписаны."
        
        await message.answer(
            "Бот запущен\n"
            "Команды:\n"
            "/val - включить рассылку\n"
            "/sval - выключить рассылку\n"
            "статистика - просмотр активности\n"
            "RP-команды - список через /rp_commands\n"
            + response
        )

    @dp.message(Command('val'))
    async def start_sending_values(message: types.Message):
        async with config.lock:
            config.is_sending_values = True
        await message.answer("Рассылка активирована")

    @dp.message(Command('sval'))
    async def stop_sending_values(message: types.Message):
        async with config.lock:
            config.is_sending_values = False
        await message.answer("Рассылка отключена")

async def monitoring_task(config: BotConfig, bot: Bot):
    """Фоновая задача мониторинга значений"""
    while True:
        if config.is_sending_values:
            new_value = await BotServices(config).read_value_from_file()
            if new_value and new_value != config.last_value:
                config.last_value = new_value
                async with config.lock:
                    users = config.subscribed_users.copy()
                
                for user_id in users:
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚠️ Обнаружено движение! Всего: {new_value}"
                        )
                    except Exception as e:
                        logger.error(f"Send error to {user_id}: {e}")
        await asyncio.sleep(2)

async def jokes_task(bot: Bot):
    """Фоновая задача отправки анекдотов"""
    while True:
        try:
            response = requests.get(
                "https://www.anekdot.ru/random/anekdot/",
                timeout=10
            )
            if response.ok:
                soup = BeautifulSoup(response.text, 'html.parser')
                if jokes := soup.find_all('div', class_='text'):
                    await bot.send_message(
                        CHANNEL_ID,
                        f"🎭 {choice(jokes).text.strip()}"
                    )
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Jokes error: {e}")
            await asyncio.sleep(60)

async def main():
    """Основная функция инициализации"""
    # Настройка логгера
    logger.add(
        "bot.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="1 MB",
        compression="zip",
        backtrace=True,
        diagnose=True
    )
    
    # Инициализация компонентов
    config = BotConfig()
    services = BotServices(config)
    bot = Bot(token=TOKEN, default=config.bot_properties)
    dp = Dispatcher()

    # Регистрация обработчиков
    await setup_bot_handlers(dp, config, services)
    setup_all_handlers(dp)  # Регистрируем обработчики статистики
    
    # Загрузка данных
    await services.load_subscribed_users()

    logger.info("Bot started")
    async with bot:
        await bot.delete_webhook(drop_pending_updates=True)
        tasks = [
            asyncio.create_task(monitoring_task(config, bot)),
            asyncio.create_task(jokes_task(bot)),
            asyncio.create_task(dp.start_polling(bot))
        ]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Bot shutdown requested")
        finally:
            for task in tasks:
                task.cancel()
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
