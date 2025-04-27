import os
import json
import random
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from contextlib import suppress
from random import choice

import dotenv
import ollama
import requests
from bs4 import BeautifulSoup
from loguru import logger
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    Sticker,
    Voice,
    PhotoSize
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hide_link

# Инициализация окружения
dotenv.load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Конфигурация
HISTORY_DIR = Path("user_history")
DATA_DIR = Path("data")
HISTORY_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
ANALYTICS_FILE = HISTORY_DIR / "analytics.json"

class BotConfig:
    def __init__(self):
        self.FILE_PATH = DATA_DIR / 'value.txt'
        self.USER_FILE_PATH = DATA_DIR / 'subscribed_users.txt'
        self.bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
        self.last_value = None
        self.subscribed_users = set()
        self.is_sending_values = False
        self.lock = asyncio.Lock()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
config = BotConfig()

class BotServices:
    def __init__(self):
        self.config = config
    
    async def load_subscribed_users(self):
        if self.config.USER_FILE_PATH.exists():
            async with self.config.lock:
                with open(self.config.USER_FILE_PATH, 'r') as file:
                    self.config.subscribed_users = {
                        int(line.strip()) for line in file if line.strip().isdigit()
                    }

    async def save_subscribed_user(self, user_id: int):
        async with self.config.lock:
            with open(self.config.USER_FILE_PATH, 'a') as file:
                file.write(f"{user_id}\n")
            logger.info(f"User {user_id} subscribed")

    async def read_value_from_file(self):
        try:
            with open(self.config.FILE_PATH, 'r') as file:
                if line := file.readline().strip():
                    if line.startswith("check = "):
                        return line.split('=')[1].strip()
        except Exception as e:
            logger.error(f"File read error: {e}")
        return None

class AnalyticsManager:
    @staticmethod
    def _ensure_analytics_file():
        if not ANALYTICS_FILE.exists():
            ANALYTICS_FILE.write_text(json.dumps({
                "total_users": 0,
                "active_users": set(),
                "usage_stats": {},
                "ratings": {}
            }))

    @classmethod
    async def log_interaction(cls, user_id: int, mode: str):
        cls._ensure_analytics_file()
        data = json.loads(ANALYTICS_FILE.read_text())
        
        data["total_users"] = max(data["total_users"], user_id)
        data["active_users"].add(str(user_id))
        
        user_stats = data["usage_stats"].get(str(user_id), {
            "last_mode": mode,
            "count": 0,
            "last_active": datetime.now().isoformat()
        })
        user_stats["count"] += 1
        data["usage_stats"][str(user_id)] = user_stats
        
        ANALYTICS_FILE.write_text(json.dumps(data))

    @classmethod
    async def log_rating(cls, user_id: int, rating: int, message: str):
        cls._ensure_analytics_file()
        data = json.loads(ANALYTICS_FILE.read_text())
        
        ratings = data["ratings"].get(str(user_id), [])
        ratings.append({
            "rating": rating,
            "message": message[:500],
            "timestamp": datetime.now().isoformat()
        })
        data["ratings"][str(user_id)] = ratings
        
        ANALYTICS_FILE.write_text(json.dumps(data))

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
            logger.error(f"Error loading stickers: {e}")

    async def fetch_stickers(self):
        try:
            for mode, pack_name in self.sticker_packs.items():
                stickerset = await bot.get_sticker_set(pack_name)
                self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]
            
            with open("stickers_cache.json", "w") as f:
                json.dump(self.stickers, f)
        except Exception as e:
            logger.error(f"Error fetching stickers: {e}")

    def get_random_sticker(self, mode: str) -> Optional[str]:
        return random.choice(self.stickers[mode]) if self.stickers[mode] else None

sticker_manager = StickerManager()
services = BotServices()

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
    def get_modes(cls) -> List[Tuple[str, str]]:
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
            logger.error(f"Ollama error ({mode}): {e}")
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
        logger.error(f"Send message error: {e}")
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
        logger.error(f"Typing error: {e}")
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
        logger.error(f"Reset error: {e}")
        await message.answer("Ошибка при очистке истории 😕")

@dp.message(Command("help"))
async def help_handler(message: Message):
    help_text = f"""
{hide_link('https://example.com/bot-preview.jpg')}
<b>📚 Доступные команды:</b>

/msg - Начать общение (выбор режима)
/reset - Очистить историю диалога
/stats - Персональная статистика
/val - Включить мониторинг
/sval - Выключить мониторинг
/help - Эта справка

<b>🌈 Режимы общения:</b>
🌸 <b>Сахароза</b> - дерзкая, но милая девушка
😈 <b>ДедИнсайд</b> - харизматичный парень
🧠 <b>Режим Гения</b> - развернутые экспертные ответы

<b>🎁 Дополнительные функции:</b>
- Мониторинг значений в файле
- Ежедневные анекдоты
- Оценка ответов (кнопки 👍/👎)
- Статистика использования (/stats)
"""
    await message.answer(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command("stats"))
async def stats_handler(message: Message):
    user_id = message.from_user.id
    data = json.loads(ANALYTICS_FILE.read_text()) if ANALYTICS_FILE.exists() else {}
    
    user_stats = data.get("usage_stats", {}).get(str(user_id), {})
    
    stats_text = (
        f"📊 <b>Ваша статистика:</b>\n\n"
        f"• Всего сообщений: {user_stats.get('count', 0)}\n"
        f"• Любимый режим: {user_stats.get('last_mode', 'еще не выбран')}\n"
        f"• Последняя активность: {user_stats.get('last_active', 'еще не активен')}\n"
        f"• Подписка на мониторинг: {'активна ✅' if user_id in config.subscribed_users else 'неактивна ❌'}"
    )
    
    await message.answer(stats_text, parse_mode=ParseMode.HTML)

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
        await AnalyticsManager.log_interaction(user_id, mode)
        
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
        logger.error(f"Mode change error: {e}")
        await callback.answer("Ошибка при смене режима")

@dp.callback_query(F.data.startswith("rate_"))
async def rate_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    rating = callback.data.split("_")[1]
    message_text = callback.message.text
    
    await AnalyticsManager.log_rating(user_id, rating, message_text)
    await callback.answer(f"Спасибо за оценку {rating}! 😊")
    
    try:
        await callback.message.edit_reply_markup()
    except:
        pass

@dp.message(Command("val"))
async def start_sending_values(message: Message):
    async with config.lock:
        config.is_sending_values = True
    await message.answer("✅ Мониторинг активирован. Вы будете получать уведомления об изменениях.")

@dp.message(Command("sval"))
async def stop_sending_values(message: Message):
    async with config.lock:
        config.is_sending_values = False
    await message.answer("❌ Мониторинг отключен. Уведомления приходить не будут.")

@dp.message(F.photo)
async def photo_handler(message: Message):
    caption = message.caption or ""
    await message.answer(
        "📸 Спасибо за фото! Я пока не умею анализировать изображения, "
        "но обязательно сохраню его в нашу базу данных!\n"
        f"Ваш комментарий: {caption[:100]}..."
    )

@dp.message(F.voice)
async def voice_handler(message: Voice):
    await message.answer(
        "🎤 Голосовые сообщения пока не поддерживаются, но мы уже работаем над этой функцией! "
        "Пока можете написать текст."
    )

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
            msg = await typing_msg.edit_text(response)
        else:
            msg = await safe_send_message(message.chat.id, response)

        if msg:
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="👍", callback_data="rate_1"),
                InlineKeyboardButton(text="👎", callback_data="rate_0"),
            )
            await msg.edit_reply_markup(reply_markup=builder.as_markup())

        if random.random() < 0.3:
            sticker = sticker_manager.get_random_sticker(mode)
            if sticker:
                await message.answer_sticker(sticker)
                
        await AnalyticsManager.log_interaction(user_id, mode)
            
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
        logger.error(f"Error ({mode}): {e}")

async def monitoring_task():
    """Фоновая задача мониторинга значений"""
    while True:
        if config.is_sending_values:
            new_value = await services.read_value_from_file()
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

async def jokes_task():
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
            await asyncio.sleep(3600)  # Каждый час
        except Exception as e:
            logger.error(f"Jokes error: {e}")
            await asyncio.sleep(60)

async def main():
    logger.add(
        "bot.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="1 MB",
        compression="zip",
        backtrace=True,
        diagnose=True
    )
    
    await services.load_subscribed_users()
    await sticker_manager.fetch_stickers()

    logger.info("Bot started")
    async with bot:
        await bot.delete_webhook(drop_pending_updates=True)
        tasks = [
            asyncio.create_task(monitoring_task()),
            asyncio.create_task(jokes_task()),
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
