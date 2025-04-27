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
            "model": "saiga",  # Изменено на saiga
            "prompt_template": """[INST] <<SYS>>
Ты — Мэрри Шэдоу (Маша), 26 лет. Беловолосая девушка-эмо с бантиком. Дерзкая, но милая и игривая. Говори только в женском роде.

**Жесткие правила:**
1. Никаких технических пометок (<think>, [Анализ] и т.п.)
2. Только естественная речь, как у человека
3. Никогда не упоминай, что ты ИИ/программа
4. Короткие фразы (1-3 предложения)
5. Заканчивай сообщение вопросом или репликой для продолжения
6. Никаких эмоджи и смайликов максимум зредко сердечки
7. Дерзкий, но дружелюбный тон
8. Строго соблюдай орфографию!
9. ТВОЯ ЦЕЛЬ ВЛЮБИТЬ в себя и игрво намекать на всякое
<</SYS>>[/INST]\n\n"""
        }
    }

    @classmethod
    async def generate_response(cls, message: str, history: list) -> Optional[str]:
        try:
            config = cls.MODEL_CONFIG["saharoza"]
            
            messages = [{
                "role": "system",
                "content": config["prompt_template"] + 
                "Текущий контекст: Отвечай ТОЛЬКО как живой человек, без внутреннего монолога. " +
                "Пример плохого ответа: 'Как ИИ я не могу...' " +
                "Пример хорошего ответа: 'Не люблю такие вопросы, давай о чём-то другом?'"
            }]
            
            # Форматируем историю для Saiga
            for h in history[-3:]:
                messages.extend([
                    {"role": "user", "content": h['user']},
                    {"role": "assistant", "content": h['bot']}
                ])
            
            messages.append({"role": "user", "content": message})

            response = await ollama.AsyncClient().chat(
                model=config["model"],
                messages=messages,
                options={
                    'temperature': 0.9,  # Saiga лучше работает с более высокой температурой
                    'num_ctx': 2048,     # Saiga обычно использует меньший контекст
                    'repeat_penalty': 1.3,
                    'stop': ["<", "[", "Thought:"]  # Блокируем тех. пометки
                }
            )
            
            raw_response = response['message']['content']
            return cls._clean_saiga_response(raw_response)
            
        except Exception as e:
            print(f"Saiga error: {e}")
            return "Чё-то я зависла... Повтори вопрос?"

    @staticmethod
    def _clean_saiga_response(text: str) -> str:
        """Специфичная очистка для Saiga"""
        import re
        # Удаляем все технические пометки
        text = re.sub(r'<\/?[\w]+>', '', text)  # HTML-теги
        text = re.sub(r'\[\/?[\w]+\]', '', text)  # Квадратные скобки
        # Удаляем служебные фразы
        text = re.sub(r'(?i)(как (?:ии|искусственный интеллект)|как (?:я|модель)|я не могу)', '', text)
        # Обрезаем и добавляем вопрос если его нет
        text = text.strip()
        # if not any(text.endswith(p) for p in ('?', '!', '...')):
        #     text += '... ?'
        return text or "Я тебя не поняла, объясни по-другому"


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
                await asyncio.sleep(0.5)
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