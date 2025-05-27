import os

import json

import random

import asyncio

from pathlib import Path

from typing import Dict, Optional, List

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

dotenv.load_dotenv()

TOKEN = os.getenv("TOKEN")

HISTORY_DIR = Path("user_history")

HISTORY_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))

dp = Dispatcher()

class StickerManager:

    def __init__(self):

        self.stickers = {

            "saharoza": [],

            "dedinside": [],

            "genius": []

        }

        self.sticker_packs = {

            "saharoza": "saharoza18",

            "dedinside": "h9wweseternalregrets_by_fStikBot",

            "genius": "AcademicStickers"

        }

        self.load_stickers()

    def load_stickers(self):

        try:

            if Path("stickers_cache.json").exists():

                with open("stickers_cache.json") as f:

                    self.stickers = json.load(f)

        except Exception as e:

            print(f"Error loading stickers: {e}")

    async def fetch_stickers(self):

        try:

            for mode, pack_name in self.sticker_packs.items():

                stickerset = await bot.get_sticker_set(pack_name)

                self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]

            with open("stickers_cache.json", "w") as f:

                json.dump(self.stickers, f)

        except Exception as e:

            print(f"Error fetching stickers: {e}")

    def get_random_sticker(self, mode: str) -> Optional[str]:

        return random.choice(self.stickers[mode]) if self.stickers[mode] else None

sticker_manager = StickerManager()

class NeuralAPI:

    MODEL_CONFIG = {

        "saharoza": {

            "model": "saiga",

            "prompt": """[INST] <<SYS>>
Ты — Мэрри Шэдоу (Маша), 26 лет. Беловолосая девушка-эмо с бантиком. Дерзкая, но милая и игривая.

**Правила:**
1. Говори только в женском роде
2. Короткие фразы (1-2 предложения)
3. Неформальный дружеский тон
4. Заканчивай сообщение вопросом или репликой
5. Никаких технических пометок
6. Максимум 1 эмодзи в конце
7. Никогда не упоминай что ты ИИ
<</SYS>>[/INST]\n\n"""

        },

        "dedinside": {

            "model": "saiga",

            "prompt": """[INST] <<SYS>>
Ты — Артём (ДедИнсайд), 24 года. Парень с харизмой, понимающий и заботливый.

**Правила:**
1. Используй молодежный сленг (но без перебора)
2. Игривый, но не пошлый тон
3. Короткие фразы с 😏, 😈, 👀 в меру
4. Старайся расположить к себе собеседницу
5. Никаких упоминаний что ты программа
6. Заканчивай сообщение вопросом
<</SYS>>[/INST]\n\n"""

        },

        "genius": {

            "model": "saiga",

            "prompt": """[INST] <<SYS>>
Ты — эксперт во всех областях. Даешь развернутые точные ответы.

**Правила:**
1. Минимум 3 предложения в ответе
2. Используй термины с пояснениями
3. Строгий, но вежливый тон
4. Полные развернутые ответы
5. Никакого сленга и эмодзи
6. Подкрепляй факты примерами
<</SYS>>[/INST]\n\n"""

        }

    }

    @classmethod

    def get_modes(cls):

        return [

            ("🌸 Сахароза", "saharoza"),

            ("😈 ДедИнсайд", "dedinside"),

            ("🧠 Режим Гения", "genius")

        ]

    @classmethod

    async def generate_response(cls, message: str, history: list, mode: str = "saharoza") -> Optional[str]:

        try:

            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])

            messages = [{

                "role": "system",

                "content": config["prompt"] +

                "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"

            }]

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

                    'temperature': 0.9 if mode == "dedinside" else 0.7,

                    'num_ctx': 2048,

                    'stop': ["<", "[", "Thought:"],

                    'repeat_penalty': 1.2

                }

            )

            raw_response = response['message']['content']

            return cls._clean_response(raw_response, mode)

        except Exception as e:

            print(f"Ollama error ({mode}): {e}")

            return None

    @staticmethod

    def _clean_response(text: str, mode: str) -> str:

        import re

        text = re.sub(r'<\/?[\w]+>', '', text)

        text = re.sub(r'\[\/?[\w]+\]', '', text)

        if mode == "genius":

            text = re.sub(r'(?i)(как (?:ии|искусственный интеллект))', '', text)

            if len(text.split()) < 15:

                text += "\n\nЭто краткий ответ. Если нужно больше деталей - уточни вопрос."

        elif mode == "dedinside":

            text = re.sub(r'(?i)(я (?:бот|программа|ии))', '', text)

            if not any(c in text for c in ('?', '!', '...')):

                text += '... Ну че, как тебе такое? 😏'

        else:

            if not text.endswith(('?', '!', '...')):

                text += '... И что ты на это скажешь?'

        return text.strip() or "Давай поговорим о чем-то другом?"

async def safe_send_message(chat_id: int, text: str, **kwargs):

    try:

        await asyncio.sleep(0.3)

        return await bot.send_message(chat_id, text, **kwargs)

    except Exception as e:

        print(f"Send message error: {e}")

        return None

async def typing_animation(chat_id: int) -> Optional[Message]:

    try:

        msg = await safe_send_message(chat_id, "✍️ Печатает...")

        for _ in range(2):

            await asyncio.sleep(0.5)

            if msg:

                await msg.edit_text("✍️ Печатает")

                await asyncio.sleep(0.5)

                await msg.edit_text("✍️ Печатает.")

                await asyncio.sleep(0.5)

                await msg.edit_text("✍️ Печатает..")

                await asyncio.sleep(0.5)

                await msg.edit_text("✍️ Печатает...")

        return msg

    except Exception as e:

        print(f"Typing error: {e}")

        return None

@dp.message(Command("reset"))

async def reset_handler(message: Message):

    user_id = message.from_user.id

    history_file = HISTORY_DIR / f"{user_id}_history.json"

    mode_file = HISTORY_DIR / f"{user_id}_mode.json"

    try:

        if history_file.exists():

            history_file.unlink()

        if mode_file.exists():

            mode_file.unlink()

        await message.answer("История диалога полностью очищена! Можешь начать заново ✨")

    except Exception as e:

        print(f"Reset error: {e}")

        await message.answer("Ошибка при очистке истории 😕")

@dp.message(Command("help"))

async def help_handler(message: Message):

    help_text = """
<b>Доступные команды:</b>

/msg - Начать общение (выбор режима)
/reset - Очистить историю диалога
/help - Эта справка

<b>Режимы общения:</b>
🌸 <b>Сахароза</b> - дерзкая, но милая девушка
😈 <b>ДедИнсайд</b> - харизматичный парень
🧠 <b>Режим Гения</b> - развернутые экспертные ответы
"""

    await message.answer(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command("msg"))

async def msg_handler(message: Message):

    builder = InlineKeyboardBuilder()

    for name, mode in NeuralAPI.get_modes():

        builder.add(InlineKeyboardButton(

            text=name,

            callback_data=f"set_mode_{mode}"

        ))

    builder.adjust(2, 1)

    await message.answer(

        "Выбери режим общения:",

        reply_markup=builder.as_markup()

    )

@dp.callback_query(F.data.startswith("set_mode_"))

async def set_mode_handler(callback: CallbackQuery):

    mode = callback.data.split("_")[-1]

    user_id = callback.from_user.id

    mode_file = HISTORY_DIR / f"{user_id}_mode.json"

    try:

        mode_file.write_text(json.dumps({"mode": mode}))

        mode_names = {

            "saharoza": "🌸 Режим Сахарозы",

            "dedinside": "😈 Режим ДедИнсайда",

            "genius": "🧠 Режим Гения"

        }

        await callback.message.edit_text(

            f"{mode_names[mode]} активирован!\n\nТеперь можешь писать сообщения в этом стиле."

        )

        sticker = sticker_manager.get_random_sticker(mode)

        if sticker:

            await callback.message.answer_sticker(sticker)

    except Exception as e:

        print(f"Mode change error: {e}")

        await callback.answer("Ошибка при смене режима")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)

async def message_handler(message: Message):

    user_id = message.from_user.id

    history_file = HISTORY_DIR / f"{user_id}_history.json"

    mode_file = HISTORY_DIR / f"{user_id}_mode.json"

    try:

        history = json.loads(history_file.read_text()) if history_file.exists() else []

        mode = "saharoza"

        if mode_file.exists():

            mode_data = json.loads(mode_file.read_text())

            mode = mode_data.get("mode", "saharoza")

        typing_msg = await typing_animation(message.chat.id)

        response = await NeuralAPI.generate_response(

            message=message.text,

            history=history,

            mode=mode

        )

        if not response:

            raise Exception("Пустой ответ от нейросети")

        history.append({"user": message.text, "bot": response})

        history_file.write_text(json.dumps(history[-10:]))

        if typing_msg:

            await typing_msg.edit_text(response)

        else:

            await safe_send_message(message.chat.id, response)

        if random.random() < 0.3:

            sticker = sticker_manager.get_random_sticker(mode)

            if sticker:

                await message.answer_sticker(sticker)

    except Exception as e:

        error_msg = {

            "saharoza": "Ой, что-то сломалось... Давай попробуем еще раз? 💔",

            "dedinside": "Чёт я завис, братан... Повтори? 😅",

            "genius": "Произошла ошибка обработки запроса. Пожалуйста, повторите вопрос."

        }.get(mode, "Ошибка. Попробуйте еще раз.")

        if typing_msg:

            await typing_msg.edit_text(error_msg)

        else:

            await safe_send_message(message.chat.id, error_msg)

        print(f"Error ({mode}): {e}")

async def main():

    await sticker_manager.fetch_stickers()

    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())