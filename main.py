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


async def main():
    logger.add("file.log",
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               rotation="3 days",
               backtrace=True,
               diagnose=True)

    bot = Bot(token=TOKEN)
    logger.info("Создан бот")
    dp = Dispatcher()
    logger.info("Создан Диспетчер")

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

                await bot.send_message(CHANNEL_ID, f"Анекдот: {anekdot}")
                logger.info(f"Бот рассказал: {anekdot}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения {e}")

            await asyncio.sleep(30)

    @dp.message(Command('soup'))
    async def send_welcome(message: types.Message):
        await message.answer("еуеуе")
        logger.info("тест")

    @dp.message(Command('start'))
    async def send_welcome(message: types.Message):
        await message.answer("Боте в строю и будет отправлять анекдоты, честна 😈")
        logger.info("Бот запущен!")

    task = asyncio.create_task(send_random_joke())

    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await bot.session.close()
        logger.info("Бот остановлен!")



if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')
