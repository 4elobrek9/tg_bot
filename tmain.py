import asyncio
import os
from loguru import logger
from dotenv import load_dotenv, find_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import requests
from bs4 import BeautifulSoup
from random import choice
from group_chat_rp import setup_group_handlers
# from channel import setup_channel_handlers

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

    # setup_private_handlers(dp)
    setup_group_handlers(dp)
    # setup_channel_handlers(dp, bot)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
    
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')