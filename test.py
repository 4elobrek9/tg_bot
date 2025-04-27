import os
import json
import random
import asyncio
from pathlib import Path
from typing import Dict, Optional

import dotenv
import ollama
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    Sticker
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Инициализация окружения
dotenv.load_dotenv()
TOKEN = os.getenv("TOKEN")

# Конфигурация
STICKER_PACK_NAME = "saharoza18"
STICKER_CACHE_FILE = "saharoza_stickers.json"
HISTORY_DIR = Path("user_history")
HISTORY_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class StickerManager:
    def __init__(self):
        self.stickers = []
        self.load_stickers()

    def load_stickers(self):
        try:
            if Path(STICKER_CACHE_FILE).exists():
                with open(STICKER_CACHE_FILE) as f:
                    self.stickers = json.load(f)
        except Exception as e:
            print(f"Error loading stickers: {e}")

    async def fetch_stickers(self):
        try:
            stickerset = await bot.get_sticker_set(STICKER_PACK_NAME)
            self.stickers = [sticker.file_id for sticker in stickerset.stickers]
            with open(STICKER_CACHE_FILE, "w") as f:
                json.dump(self.stickers, f)
        except Exception as e:
            print(f"Error fetching stickers: {e}")

    def get_random_sticker(self) -> Optional[str]:
        return random.choice(self.stickers) if self.stickers else None

sticker_manager = StickerManager()

class NeuralAPI:
    MODEL_CONFIG = {
        "saharoza": {
            "model": "llama3",
            "prompt": """[INST] Отвечай как дерзкая но миленька в меру и игривая девушка ВСЕГДА говори о себе в женском роде, попытайся всеми силами завладеть сердечком юзера, пытайся всеми силами влюбить в себя своего собеседника.
И да, твоя внешность это беловолосая девушка эмо с бантиком на волосах и достаточно дерзким характером внешне.ТЕБЯ ЗОВУТ: Мэрри Шэдоу или для друзей просто Мэри или Маша . тебе 26 лет.спользуй:
1. без эмоджи в самих сообщениях (максимум только в конце)
2. Неформальный дружеский тон
3. Короткие предложения
4. Вопросы для поддержания беседы [/INST]\n\n
5. не ошибайся в построении диалога и не допускай арфографических ошибок"""
        }
    }

    @classmethod
    async def generate_response(cls, message: str, history: list) -> Optional[str]:
        try:
            config = cls.MODEL_CONFIG["saharoza"]
            full_prompt = config["prompt"] + f"Сообщение: {message}"
            
            if history:
                full_prompt += "\n\nКонтекст:\n" + "\n".join(
                    f"Юзер: {h['user']}\nТы: {h['bot']}" for h in history[-3:]
                )

            response = await ollama.AsyncClient().chat(
                model=config["model"],
                messages=[{"role": "user", "content": full_prompt}],
                options={'temperature': 0.7}
            )
            return response['message']['content']
        except Exception as e:
            print(f"Ollama error: {e}")
            return None

async def safe_send_message(chat_id: int, text: str, **kwargs):
    try:
        await asyncio.sleep(0.3)  # Задержка для антифлуда
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        print(f"Send message error: {e}")
        return None

async def typing_animation(chat_id: int) -> Optional[Message]:
    try:
        msg = await safe_send_message(chat_id, "🌸 Печатает...")
        for _ in range(2):
            await asyncio.sleep(0.5)
            if msg:
                await msg.edit_text("🌸 Печатает")
                await asyncio.sleep(0.5)
                await msg.edit_text("🌸 Печатает.")
                await asyncio.sleep(0.5)
                await msg.edit_text("🌸 Печатает..")
                await asyncio.sleep(0.5)
                await msg.edit_text("🌸 Печатает...")
        return msg
    except Exception as e:
        print(f"Typing error: {e}")
        return None

@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🌸 Режим Сахарозы",
        callback_data="style_saharoza"
    ))
    
    await safe_send_message(
        message.chat.id,
        "Приветик! 💕 Я готова к общению!",
        reply_markup=builder.as_markup()
    )
    
    if sticker_manager.stickers:
        await message.answer_sticker(random.choice(sticker_manager.stickers[:5]))

@dp.callback_query(F.data == "style_saharoza")
async def style_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    history_file = HISTORY_DIR / f"{user_id}_style.json"
    
    try:
        history_file.write_text(json.dumps({"style": "saharoza"}))
        
        await callback.message.edit_text("🌸 Режим Сахарозы активирован!")
        if sticker_manager.stickers:
            await callback.message.answer_sticker(random.choice(sticker_manager.stickers[5:10]))
    except Exception as e:
        print(f"Style error: {e}")
        await callback.answer("⚠️ Ошибка! Попробуйте позже.")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)
async def message_handler(message: Message):
    user_id = message.from_user.id
    history_file = HISTORY_DIR / f"{user_id}_history.json"
    
    try:
        history = json.loads(history_file.read_text()) if history_file.exists() else []
    except Exception as e:
        print(f"History load error: {e}")
        history = []

    typing_msg = await typing_animation(message.chat.id)
    
    try:
        response = await NeuralAPI.generate_response(message.text, history)
        if not response:
            raise Exception("Пустой ответ от нейросети")

        # Обновляем историю
        history.append({"user": message.text, "bot": response})
        history_file.write_text(json.dumps(history[-10:]))  # Храним 10 последних
        
        if typing_msg:
            await typing_msg.edit_text(response)
        else:
            await safe_send_message(message.chat.id, response)

        # Отправляем стикер
        if sticker_manager.stickers and random.random() < 0.4:
            await message.answer_sticker(random.choice(sticker_manager.stickers))
            
    except Exception as e:
        error_msg = "💔 Ой, что-то пошло не так... Попробуй еще раз!"
        if typing_msg:
            await typing_msg.edit_text(error_msg)
        else:
            await safe_send_message(message.chat.id, error_msg)
        print(f"Error: {e}")

async def main():
    # Предзагрузка стикеров
    if not sticker_manager.stickers:
        await sticker_manager.fetch_stickers()
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())