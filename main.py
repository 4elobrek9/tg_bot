import asyncio
import os
from loguru import logger
from dotenv import load_dotenv, find_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import requests
from bs4 import BeautifulSoup
from random import choice
from group_chat_stat import setup_stat_handlers
from group_chat_rp import setup_rp_handlers

load_dotenv(find_dotenv())
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(token=TOKEN)
logger.info("Создан бот")

# Пути к файлам
FILE_PATH = 'C:/Users/motion-detector/value.txt'
USER_FILE_PATH = 'subscribed_users.txt'
last_value = None
subscribed_users = set()
is_sending_values = False

async def load_subscribed_users():
    """Загружаем список подписанных пользователей"""
    if os.path.exists(USER_FILE_PATH):
        with open(USER_FILE_PATH, 'r') as file:
            for line in file:
                user_id = line.strip()
                if user_id.isdigit():
                    subscribed_users.add(int(user_id))

async def save_subscribed_user(user_id):
    """Сохраняем ID подписавшегося пользователя"""
    with open(USER_FILE_PATH, 'a') as file:
        file.write(f"{user_id}\n")
    logger.info(f"Пользователь {user_id} добавлен в список подписчиков.")

async def read_value_from_file():
    """Чтение значения из файла"""
    try:
        with open(FILE_PATH, 'r') as file:
            line = file.readline().strip()
            if line.startswith("check = "):
                return line.split('=')[1].strip()
    except Exception as e:
        logger.error(f"Ошибка при чтении файла: {e}")
    return None

async def update_telegram_message():
    """Обновление и рассылка значений"""
    global last_value
    while True:
        if is_sending_values:
            new_value = await read_value_from_file()
            if new_value and new_value != last_value:
                last_value = new_value
                for user_id in subscribed_users:
                    await bot.send_message(
                        user_id, 
                        f"ВНИМАНИЕ ЗАФИКСИРОВАНО ДВИЖЕНИЕ! Всего было движений: {new_value}"
                    )
        await asyncio.sleep(2)

async def send_random_joke():
    """Отправка случайных анекдотов"""
    while True:
        try:
            response = requests.get("https://www.anekdot.ru/random/anekdot/")
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                jokes = soup.find_all('div', class_='text')
                anekdot = choice(jokes).text.strip()
            else:
                anekdot = 'Не удалось получить анекдот'

            await bot.send_message(CHANNEL_ID, f"Шутка: {anekdot}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")

        await asyncio.sleep(30)

async def main():
    """Основная функция бота"""
    logger.info("Инициализация бота...")
    logger.add(
        "file.log",
        format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
        rotation="3 days",
        backtrace=True,
        diagnose=True
    )

    # Создаем диспетчер
    dp = Dispatcher()
    logger.info("Диспетчер создан")
    
    # Подключаем модули
    dp = setup_stat_handlers(dp)
    dp = setup_rp_handlers(dp)
    logger.info("Модули подключены")

    # Обработчики команд
    @dp.message(Command('start'))
    async def send_welcome(message: types.Message):
        await message.answer(
            "Бот запущен, сигналка работает\n"
            "чтобы рассылку отключить пропиши /sval\n"
            "Для статистики активности используйте 'статистика'\n"
            "Для RP-действий используйте соответствующие команды"
        )
        user_id = message.from_user.id
        if user_id not in subscribed_users:
            subscribed_users.add(user_id)
            await save_subscribed_user(user_id)
            await message.answer("Вы подписались на рассылку значений.")
        else:
            await message.answer("Вы уже подписаны на рассылку значений.")

    @dp.message(Command('val'))
    async def start_sending_values(message: types.Message):
        global is_sending_values
        is_sending_values = True
        await message.answer("Рассылка значений включена.")

    @dp.message(Command('sval'))
    async def stop_sending_values(message: types.Message):
        global is_sending_values
        is_sending_values = False
        await message.answer("Рассылка значений выключена.\nвключить можно с помощью /val")

    # Запускаем фоновые задачи
    await load_subscribed_users()
    tasks = [
        asyncio.create_task(send_random_joke()),
        asyncio.create_task(update_telegram_message())
    ]

    try:
        logger.info("Запущен без ошибок...")
        await dp.start_polling(bot)
    finally:
        logger.info("Остановка бота...")
        for task in tasks:
            task.cancel()
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот выключен по запросу пользователя")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")