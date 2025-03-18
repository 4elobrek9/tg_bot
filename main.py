import asyncio
import os
from loguru import logger
from dotenv import load_dotenv, find_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import requests
from bs4 import BeautifulSoup
from random import choice

load_dotenv(find_dotenv())
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(token=TOKEN)
logger.info("Создан бот")
dp = Dispatcher()
logger.info("Создан Диспетчер")

# Путь к текстовому файлу
FILE_PATH = 'C:/Users/aboby/motion-detector/value.txt'
USER_FILE_PATH = 'subscribed_users.txt'  # Путь к файлу для хранения ID пользователей
last_value = None  # Переменная для хранения последнего значения
subscribed_users = set()  # Множество для хранения ID пользователей, подписанных на рассылку
is_sending_values = False  # Флаг для управления рассылкой значений

async def load_subscribed_users():
    """Загрузить подписанных пользователей из файла."""
    if os.path.exists(USER_FILE_PATH):
        with open(USER_FILE_PATH, 'r') as file:
            for line in file:
                user_id = line.strip()
                if user_id.isdigit():
                    subscribed_users.add(int(user_id))
    logger.info(f"Загружено подписанных пользователей: {subscribed_users}")

async def save_subscribed_user(user_id):
    """Сохранить ID пользователя в файл."""
    with open(USER_FILE_PATH, 'a') as file:
        file.write(f"{user_id}\n")
    logger.info(f"Пользователь {user_id} добавлен в список подписчиков.")

async def read_value_from_file():
    try:
        with open(FILE_PATH, 'r') as file:
            line = file.readline().strip()
            # Извлекаем число из строки формата "check = <число>"
            if line.startswith("check = "):
                current_value = line.split('=')[1].strip()
                return current_value
    except Exception as e:
        logger.error(f"Ошибка при чтении файла: {e}")
    return None

async def update_telegram_message():
    global last_value
    while True:
        if is_sending_values:  # Проверяем, включена ли рассылка
            new_value = await read_value_from_file()
            if new_value and new_value != last_value:
                last_value = new_value
                for user_id in subscribed_users:
                    await bot.send_message(user_id, f"ВНИМАНИЕ ЗАФИКСИРОВАНО ДВИЖЕНИЕ! Всего было движений: {new_value}")
                    logger.info(f"Отправлено новое значение пользователю {user_id}: {new_value}")
        await asyncio.sleep(2)

async def send_random_joke():
    while True:
        try:
            response = requests.get("https://www.anekdot.ru/random/anekdot/")
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                jokes = soup.find_all('div', class_='text')
                random_joke = choice(jokes).text.strip()
                anekdot = random_joke
            else:
                anekdot = 'Не удалось получить анекдот'

            await bot.send_message(CHANNEL_ID, f"Шутка: {anekdot}")
            logger.info(f"Бот рассказал: {anekdot}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")

        await asyncio.sleep(30)

@dp.message(Command('start'))
async def send_welcome(message: types.Message):
    await message.answer("Бот запущен, сигналка работает\nчтобы рассылку отключить пропиши /sval")
    logger.info("Бот запущен!")
    user_id = message.from_user.id
    if user_id not in subscribed_users:  # Проверяем, подписан ли пользователь
        subscribed_users.add(user_id)  # Добавляем пользователя в список подписчиков
        await save_subscribed_user(user_id)  # Сохраняем ID пользователя в файл
        await message.answer("Вы подписались на рассылку значений.")
    else:
        await message.answer("Вы уже подписаны на рассылку значений.")

@dp.message(Command('val'))
async def start_sending_values(message: types.Message):
    global is_sending_values
    is_sending_values = True
    await message.answer("Рассылка значений включена.")
    logger.info(f"Рассылка значений включена для пользователя {message.from_user.id}.")

@dp.message(Command('sval'))
async def stop_sending_values(message: types.Message):
    global is_sending_values
    is_sending_values = False
    await message.answer("Рассылка значений выключена.\nвключить можно с помощью /val")
    logger.info(f"Рассылка значений выключена для пользователя {message.from_user.id}.")

async def main():
    logger.add("file.log",
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               rotation="3 days",
               backtrace=True,
               diagnose=True)

    await load_subscribed_users()  # Загружаем подписанных пользователей
    task_joke = asyncio.create_task(send_random_joke())
    task_value = asyncio.create_task(update_telegram_message())  # Запускаем задачу для отправки значений

    try:
        await dp.start_polling(bot)
    finally:
        task_joke.cancel()
        task_value.cancel()
        await bot.session.close()
        logger.info("Бот остановлен!")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')
