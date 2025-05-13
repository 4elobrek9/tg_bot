# main_refactored.py
import os
import json
import random
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from contextlib import suppress
from random import choice
import logging 
import aiosqlite
from pydantic import ValidationError
from group_stat import setup_stat_handlers, ProfileManager
import database as db 
from rp_module_refactored import setup_rp_handlers

import dotenv
import ollama
import aiohttp
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    Sticker,
    Voice, # Voice тип не используется как F.voice, но для аннотации можно оставить
    PhotoSize
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hide_link, hbold, hitalic, hcode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

dotenv.load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID") # ID администратора для пересылки дизлайков

ADMIN_USER_ID: Optional[int] = None
if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
else:
    logger.warning("ADMIN_USER_ID is not set or invalid in .env file. Dislike forwarding will be disabled.")

if not TOKEN:
    logger.critical("Bot token not found in environment variables (TOKEN)")
    exit()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
VALUE_FILE_PATH = DATA_DIR / 'value.txt' 

MAX_RATING_OPPORTUNITIES = 3 # Максимальное количество сообщений, которые можно оценить

class MonitoringState:
    def __init__(self):
        self.is_sending_values = False
        self.last_value = None
        self.lock = asyncio.Lock()

monitoring_state = MonitoringState()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- StickerManager (код без изменений, как в предыдущем ответе) ---
class StickerManager:
    def __init__(self):
        self.stickers = { "saharoza": [], "dedinside": [], "genius": [] }
        self.sticker_packs = {
            "saharoza": "saharoza18",
            "dedinside": "h9wweseternalregrets_by_fStikBot",
            "genius": "AcademicStickers"
        }
        self.cache_file = Path("stickers_cache.json")
        self.load_stickers_from_cache()

    def load_stickers_from_cache(self):
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, dict) and all(k in cached_data for k in self.sticker_packs):
                         self.stickers = cached_data
                         logger.info("Stickers loaded from cache.")
                    else:
                         logger.warning("Sticker cache file has incorrect format. Re-fetching.")
            else:
                 logger.info("Sticker cache not found.")
        except Exception as e:
            logger.error(f"Error loading stickers from cache: {e}")

    async def fetch_stickers(self, bot_instance: Bot):
        logger.info("Fetching stickers from Telegram...")
        try:
            all_fetched = True
            for mode, pack_name in self.sticker_packs.items():
                try:
                    stickerset = await bot_instance.get_sticker_set(pack_name)
                    self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]
                    logger.info(f"Fetched {len(self.stickers[mode])} stickers for mode '{mode}'.")
                except Exception as e:
                    logger.error(f"Failed to fetch sticker set '{pack_name}' for mode '{mode}': {e}")
                    all_fetched = False
            if all_fetched: self.save_stickers_to_cache()
        except Exception as e:
            logger.error(f"General error fetching stickers: {e}")

    def save_stickers_to_cache(self):
        try:
            with open(self.cache_file, "w", encoding='utf-8') as f:
                json.dump(self.stickers, f, ensure_ascii=False, indent=4)
            logger.info("Stickers saved to cache.")
        except Exception as e:
            logger.error(f"Error saving stickers to cache: {e}")

    def get_random_sticker(self, mode: str) -> Optional[str]:
        return random.choice(self.stickers[mode]) if self.stickers.get(mode) else None

sticker_manager = StickerManager()

# --- NeuralAPI (код без изменений, как в предыдущем ответе) ---
class NeuralAPI:
    MODEL_CONFIG = {
        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Мэрри Шэдоу (Маша), 26 лет... <</SYS>>[/INST]\n\n"},
        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Артём (ДедИнсайд), 24 года... <</SYS>>[/INST]\n\n"},
        "genius": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — эксперт во всех областях... <</SYS>>[/INST]\n\n"}
    } # Сократил промпты для краткости, вставляй полные

    @classmethod
    def get_modes(cls) -> List[Tuple[str, str]]:
        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod
    async def generate_response(cls, message: str, history_ollama_format: list, mode: str = "saharoza") -> Optional[str]:
        try:
            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
            
            # 1. Системный промпт
            messages_payload = [{
                "role": "system", 
                "content": config["prompt"] + "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"
            }]
            
            # 2. Форматирование истории из [{"user": u, "bot": b}] в [{"role":"user", "content":u}, {"role":"assistant", "content":b}]
            for history_item in history_ollama_format:
                if "user" in history_item and history_item["user"]: # Проверяем наличие и непустое значение
                    messages_payload.append({"role": "user", "content": history_item["user"]})
                if "bot" in history_item and history_item["bot"]:   # Проверяем наличие и непустое значение
                    messages_payload.append({"role": "assistant", "content": history_item["bot"]})

            # 3. Текущее сообщение пользователя
            messages_payload.append({"role": "user", "content": message})

            # Вызов Ollama без async with
            client = ollama.AsyncClient() 
            response = await client.chat(
                model=config["model"], 
                messages=messages_payload, # Передаем правильно отформатированный список
                options={'temperature': 0.9 if mode == "dedinside" else 0.7, 'num_ctx': 2048, 'stop': ["<", "[", "Thought:"], 'repeat_penalty': 1.2}
            )
            
            raw_response = response['message']['content']
            return cls._clean_response(raw_response, mode)
            
        except ollama.ResponseError as e:
            error_details = getattr(e, 'error', str(e)) 
            logger.error(f"Ollama API Error ({mode}): Status {e.status_code}, Response: {error_details}")
            return f"Ой, кажется, модель '{config['model']}' сейчас не отвечает (Ошибка {e.status_code}). Попробуй позже."
        # Добавим обработку ValidationError отдельно для ясности
        except ValidationError as e: 
            logger.error(f"Ollama message validation error ({mode}): {e}", exc_info=True)
            logger.error(f"Problematic messages payload structure: {messages_payload}") # Логируем структуру для отладки
            return "Произошла ошибка при подготовке данных для нейросети. Попробуйте /reset и напишите снова."
        except Exception as e:
            logger.error(f"Ollama general error ({mode}): {e}", exc_info=True)
            return "Произошла внутренняя ошибка при обращении к нейросети. Попробуйте еще раз."

    @staticmethod
    def _clean_response(text: str, mode: str) -> str:
        import re
        text = re.sub(r'<\/?[\w\s="/.\':?]+>', '', text)
        text = re.sub(r'\[\/?[\w\s="/.\':?]+\]', '', text)
        text = re.sub(r'(^|\n)\s*Thought:.*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Okay, here is the response.*?\n', '', text, flags=re.IGNORECASE | re.MULTILINE)
        if mode == "genius":
            text = re.sub(r'(?i)(как (?:ии|искусственный интеллект|ai|language model))', '', text)
            if text and len(text.split()) < 15 and not text.startswith("Ой,") and not text.startswith("Произошла"):
                 text += "\n\nЭто краткий ответ. Если нужно больше деталей - уточни вопрос."
        elif mode == "dedinside":
            text = re.sub(r'(?i)(я (?:бот|программа|ии|модель))', '', text)
            if text and not any(c in text for c in ('?', '!', '...', '😏', '😈', '👀')): text += '... Ну че, как тебе такое? 😏'
        elif mode == "saharoza": 
             text = re.sub(r'(?i)(я (?:бот|программа|ии|модель))', '', text)
             if text and not any(c in text for c in ('?', '!', '...', '🌸', '✨', '💔', '😉')): text += '... И что ты на это скажешь? 😉'
        cleaned_text = text.strip()
        return cleaned_text if cleaned_text else "Хм, не знаю, что ответить... Спроси что-нибудь еще?"

# --- Хелперы ---
async def safe_send_message(chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        return None

async def typing_animation(chat_id: int) -> Optional[Message]:
    typing_msg = None 
    try:
        typing_msg = await bot.send_message(chat_id, "✍️ Печатает...")
        await asyncio.sleep(1.0) 
        await typing_msg.edit_text("✍️ Печатает..")
        await asyncio.sleep(1.0)
        await typing_msg.edit_text("✍️ Печатает...")
        await asyncio.sleep(1.0)
        return typing_msg
    except Exception as e:
        logger.warning(f"Typing animation error in chat {chat_id}: {e}")
        if typing_msg:
            with suppress(Exception): await typing_msg.delete()
        return None

# --- Обработчики команд ---
@dp.message(Command("start"))
async def start_handler(message: Message):
     user = message.from_user
     await db.ensure_user(user.id, user.username, user.first_name)
     await message.answer(f"Привет, {user.first_name}! 👋\nЯ твой многоликий AI-собеседник. Используй /msg для выбора режима или /help для списка команд.")

@dp.message(Command("reset"))
async def reset_handler(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    try:
        async with aiosqlite.connect(db.DB_FILE) as conn:
             await conn.execute('DELETE FROM dialog_history WHERE user_id = ?', (user.id,))
             await conn.commit()
        await db.set_user_mode(user.id, "saharoza") 
        await db.reset_rating_opportunity_count(user.id) # СБРОС СЧЕТЧИКА ОЦЕНОК
        await message.answer("История диалога и счетчик оценок сброшены! Можешь начать заново ✨")
        logger.info(f"Dialog history and rating count reset for user {user.id}")
    except Exception as e:
        logger.error(f"Reset error for user {user.id}: {e}", exc_info=True)
        await message.answer("Ошибка при сбросе 😕 Попробуй позже.")

@dp.message(Command("help"))
async def help_handler(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    help_text = f"""{hide_link('https://example.com/bot-preview.jpg')} 
<b>📚 Доступные команды:</b>
/start - Начать работу с ботом
/msg - Выбрать режим общения
/reset - Очистить историю диалога и сбросить лимит оценок (3)
/stats - Посмотреть свою статистику
/val - ✅ Включить мониторинг значения
/sval - ❌ Выключить мониторинг значения
/help - Показать эту справку
<i>(В группах: /rp_commands)</i>
<b>🌈 Режимы общения:</b>
🌸 <b>Сахароза</b> 😈 <b>ДедИнсайд</b> 🧠 <b>Режим Гения</b>
<b>🎁 Функции:</b> Мониторинг, анекдоты, оценка ответов (первые 3), статистика.""" # Упростил для краткости
    await message.answer(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command("stats"))
async def stats_handler(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    try:
        user_stats_summary = await db.get_user_stats_db(user.id)
        is_subscribed = await db.is_value_subscriber(user.id)
        user_mode_data = await db.get_user_mode_and_rating_opportunity(user.id)
        rating_opportunities_left = MAX_RATING_OPPORTUNITIES - user_mode_data.get('rating_opportunities_count', 0)

        stats_text = (
            f"📊 <b>Ваша статистика:</b>\n\n"
            f"• Всего запросов к ИИ: {user_stats_summary.get('count', 0)}\n"
            f"• Текущий режим: {user_mode_data.get('mode', 'saharoza')}\n"
            f"• Последняя активность: {user_stats_summary.get('last_active', 'еще не активен')}\n"
            f"• Подписка на мониторинг: {'активна ✅' if is_subscribed else 'неактивна ❌'}\n"
            f"• Оценок можно поставить еще: {max(0, rating_opportunities_left)}"
        )
        await message.answer(stats_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error fetching stats for user {user.id}: {e}", exc_info=True)
        await message.answer("Не удалось получить статистику.")

@dp.message(Command("msg"))
async def msg_handler_command(message: Message): # Переименовал, чтобы не конфликтовать с message_handler
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    builder = InlineKeyboardBuilder()
    for name, mode_code in NeuralAPI.get_modes():
        builder.add(InlineKeyboardButton(text=name, callback_data=f"set_mode_{mode_code}"))
    builder.adjust(1)
    await message.answer("Выбери режим общения:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_mode_"))
async def set_mode_handler(callback: CallbackQuery):
    try:
        mode = callback.data.split("_")[-1]
        user = callback.from_user
        await db.ensure_user(user.id, user.username, user.first_name)
        await db.set_user_mode(user.id, mode)
        await db.log_interaction_db(user.id, f"set_mode_to_{mode}") # Логируем как отдельное событие
        
        mode_names = {"saharoza": "🌸 Сахарозы", "dedinside": "😈 ДедИнсайда", "genius": "🧠 Гения"}
        mode_name_display = mode_names.get(mode, "Выбранный режим")
        await callback.message.edit_text(f"Режим {mode_name_display} активирован!\nТеперь можешь писать сообщения.")
        
        sticker_id = sticker_manager.get_random_sticker(mode)
        if sticker_id: await callback.message.answer_sticker(sticker_id) 
        await callback.answer(f"Режим '{mode_name_display}' установлен!")
    except Exception as e:
        logger.error(f"Mode change error for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.answer("Ошибка при смене режима 😕", show_alert=True)

@dp.callback_query(F.data.startswith("rate_"))
async def rate_handler(callback: CallbackQuery):
    global ADMIN_USER_ID # Используем глобальную переменную
    try:
        user = callback.from_user
        rating = int(callback.data.split("_")[1]) 
        message_text_preview = callback.message.text or callback.message.caption or "[Медиа сообщение]"
        
        await db.log_rating_db(user.id, rating, message_text_preview)
        feedback = "Спасибо за лайк! 👍" if rating == 1 else "Спасибо за отзыв! 👎"
        await callback.answer(feedback)
        await callback.message.edit_reply_markup(reply_markup=None)

        if rating == 0 and ADMIN_USER_ID: # Дизлайк и есть ADMIN_USER_ID
            logger.info(f"Dislike received from user {user.id} (@{user.username}). Forwarding dialog to admin {ADMIN_USER_ID}.")
            dialog_entries = await db.get_dialog_history(user.id, limit=10) # Получаем последние 10 пар (20 записей)
            
            if not dialog_entries:
                await safe_send_message(ADMIN_USER_ID, f"⚠️ Пользователь {hbold(user.full_name)} (ID: {hcode(str(user.id))}, @{user.username or 'нет'}) поставил дизлайк, но история диалога пуста.")
                return

            formatted_dialog = f"👎 Дизлайк от {hbold(user.full_name)} (ID: {hcode(str(user.id))}, @{user.username or 'нет'}).\n"
            formatted_dialog += f"Сообщение бота (режим {hitalic(dialog_entries[-1]['mode'])}):\n{hcode(message_text_preview)}\n\n" # Последнее сообщение бота - то, что оценили
            formatted_dialog += "📜 История диалога (последние сообщения):\n"
            
            full_dialog_text = ""
            for entry in dialog_entries:
                ts = datetime.fromtimestamp(entry['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                if entry['role'] == 'user':
                    full_dialog_text += f"👤 User ({ts}): {entry['content']}\n"
                else: # assistant
                    full_dialog_text += f"🤖 Bot ({entry['mode']}, {ts}): {entry['content']}\n"
            
            # Склеиваем заголовок и сам диалог
            final_report = formatted_dialog + "```\n" + full_dialog_text + "\n```" # Используем Markdown code block для лучшей читаемости

            # Отправка длинных сообщений частями
            max_len = 4000 # Чуть меньше лимита, чтобы учесть HTML теги и заголовки
            if len(final_report) > max_len:
                parts = [final_report[i:i + max_len] for i in range(0, len(final_report), max_len)]
                for i, part_text in enumerate(parts):
                    part_header = f"Часть {i+1}/{len(parts)}:\n" if len(parts) > 1 else ""
                    await safe_send_message(ADMIN_USER_ID, part_header + part_text, parse_mode=ParseMode.HTML) # Используем HTML для заголовка
            else:
                await safe_send_message(ADMIN_USER_ID, final_report, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Rating error or forwarding failed for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.answer("Ошибка при сохранении оценки.", show_alert=True)

@dp.message(Command("val"))
async def start_sending_values(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    await db.add_value_subscriber(user.id)
    async with monitoring_state.lock:
        monitoring_state.is_sending_values = True 
    await message.answer("✅ Мониторинг активирован.")
    logger.info(f"User {user.id} subscribed to value monitoring.")

@dp.message(Command("sval"))
async def stop_sending_values(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    await db.remove_value_subscriber(user.id)
    subscribers = await db.get_value_subscribers()
    if not subscribers:
        async with monitoring_state.lock:
             monitoring_state.is_sending_values = False
             logger.info("No more subscribers, value monitoring globally stopped.")
    await message.answer("❌ Мониторинг для вас отключен.")
    logger.info(f"User {user.id} unsubscribed from value monitoring.")

# --- Обработчики сообщений ---
@dp.message(F.photo)
async def photo_handler(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    caption = message.caption or ""
    await message.answer(f"📸 Фото получил! Комментарий: {caption[:100]}...")

@dp.message(F.voice)
async def voice_handler_msg(message: Message): # message: Message
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    await message.answer("🎤 Голосовые пока не обрабатываю, но работаю над этим!")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)
async def message_handler(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)

    user_mode_data = await db.get_user_mode_and_rating_opportunity(user.id)
    mode = user_mode_data.get('mode', "saharoza")
    rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)
    
    history_ollama = await db.get_dialog_history_for_ollama(user.id, limit=5)
    
    typing_msg = await typing_animation(message.chat.id)

    try:
        response = await NeuralAPI.generate_response(
            message=message.text,
            history_ollama_format=history_ollama,
            mode=mode
        )
        if not response: 
             response = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"
             logger.warning(f"Empty response from NeuralAPI for user {user.id}, mode {mode}")

        await db.add_dialog_history(user.id, mode, message.text, response)
        await db.log_interaction_db(user.id, mode)
        
        response_msg_obj = None
        if typing_msg:
            response_msg_obj = await typing_msg.edit_text(response)
        else:
            response_msg_obj = await safe_send_message(message.chat.id, response)

        if response_msg_obj and rating_opportunities_count < MAX_RATING_OPPORTUNITIES:
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="👍", callback_data="rate_1"),
                InlineKeyboardButton(text="👎", callback_data="rate_0"),
            )
            try:
                 await response_msg_obj.edit_reply_markup(reply_markup=builder.as_markup())
                 await db.increment_rating_opportunity_count(user.id) # Увеличиваем счетчик ПОСЛЕ успешного добавления кнопок
            except Exception as edit_err:
                 logger.warning(f"Could not edit reply markup for msg {response_msg_obj.message_id}: {edit_err}")
        
        if random.random() < 0.3: 
            sticker_id = sticker_manager.get_random_sticker(mode)
            if sticker_id: await message.answer_sticker(sticker_id)
                
    except Exception as e:
        logger.error(f"Error processing message for user {user.id} in mode {mode}: {e}", exc_info=True)
        error_texts = {
            "saharoza": "Ой, что-то сломалось... 💔", "dedinside": "Чёт я завис... 😅",
            "genius": "Ошибка обработки запроса."
        }
        error_msg_text = error_texts.get(mode, "Ошибка.")
        
        if typing_msg:
            try: await typing_msg.edit_text(error_msg_text)
            except Exception: await safe_send_message(message.chat.id, error_msg_text)
        else:
            await safe_send_message(message.chat.id, error_msg_text)

# --- Фоновые задачи (код без изменений, как в предыдущем ответе) ---
async def monitoring_task():
    logger.info("Monitoring task started.")
    while True:
        should_run = False
        async with monitoring_state.lock:
            if monitoring_state.is_sending_values: should_run = True
        if should_run:
            try:
                new_value = await asyncio.to_thread(db.read_value_from_file, VALUE_FILE_PATH)
                async with monitoring_state.lock:
                    if new_value is not None and new_value != monitoring_state.last_value:
                        logger.info(f"Value change: '{monitoring_state.last_value}' -> '{new_value}'")
                        monitoring_state.last_value = new_value
                        subscribers_ids = await db.get_value_subscribers()
                    else: subscribers_ids = []
                if subscribers_ids:
                    logger.info(f"Notifying {len(subscribers_ids)} value subscribers...")
                    msg_text = f"⚠️ Обнаружено движение! Всего: {new_value}"
                    tasks = [safe_send_message(uid, msg_text) for uid in subscribers_ids]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for uid, res in zip(subscribers_ids, results):
                        if isinstance(res, Exception): logger.error(f"Value notification error to {uid}: {res}")
            except Exception as e: logger.error(f"Error in monitoring_task loop: {e}", exc_info=True)
        await asyncio.sleep(5)

async def jokes_task():
    logger.info("Jokes task started.")
    if not CHANNEL_ID:
        logger.warning("Jokes task disabled: CHANNEL_ID is not set.")
        return
    try: channel_id_int = int(CHANNEL_ID)
    except ValueError:
        logger.error(f"Invalid CHANNEL_ID: {CHANNEL_ID}. Jokes task disabled.")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                logger.debug("Fetching joke...")
                async with session.get("https://www.anekdot.ru/random/anekdot/", timeout=15) as response:
                    if response.status == 200:
                        text = await response.text()
                        soup = BeautifulSoup(text, 'html.parser')
                        jokes_divs = soup.find_all('div', class_='text')
                        if jokes_divs:
                            joke_text = choice(jokes_divs).text.strip().replace('<br/>', '\n').replace('<br>', '\n').strip()
                            if joke_text:
                                await safe_send_message(channel_id_int, f"🎭 {joke_text}")
                                logger.info(f"Joke sent to channel {channel_id_int}.")
                            else: logger.warning("Parsed joke text is empty.")
                        else: logger.warning("Could not find jokes div.")
                    else: logger.warning(f"Jokes site request failed: {response.status}")
                await asyncio.sleep(3600) 
            except aiohttp.ClientError as e: logger.error(f"Jokes task network error: {e}"); await asyncio.sleep(120)
            except asyncio.TimeoutError: logger.warning("Jokes task timed out."); await asyncio.sleep(120)
            except Exception as e: logger.error(f"Jokes task unexpected error: {e}", exc_info=True); await asyncio.sleep(300)

# --- Запуск бота ---
async def main():

    # --- 3. Создание ОДНОГО экземпляра ProfileManager ---
    # Этот экземпляр будет управлять соединением с БД и предоставлять методы
    profile_manager_instance = ProfileManager()
    # Важно: Создаем его здесь, внутри асинхронной функции, а не глобально.

    # --- 4. АСИНХРОННО УСТАНОВЛЕНИЕ СОЕДИНЕНИЯ С БАЗОЙ ДАННЫХ ---
    # ЭТОТ ШАГ КРИТИЧЕСКИ ВАЖЕН для aiosqlite
    # Мы должны дождаться подключения ПЕРЕД тем, как хэндлеры смогут его использовать.
    try:
        logger.info("Attempting to connect to database...")
        await profile_manager_instance.connect() # !!! Ждем подключения !!!
        logger.info("Database connection established successfully.")
    except Exception as e:
        # Если не удалось подключиться к БД, нет смысла запускать бота
        logger.critical(f"Failed to connect to database: {e}. Shutting down.", exc_info=True)
        await bot.session.close() # Закрываем сессию бота перед выходом
        return # Прерываем выполнение функции main

    # --- 5. Настройка всех роутеров и хэндлеров ---
    # Передаем главный диспетчер в функции настройки из ваших модулей
    logger.info("Setting up handlers from modules...")
    setup_stat_handlers(dp) # Вызываем функцию настройки из group_stat.py

    # Если у вас есть другие модули, вызывайте их функции настройки здесь:
    # setup_rp_handlers(dp) # Пример вызова функции из rp_module.py

    logger.info("All handlers configured.")

    # --- 6. Запуск поллинга (приема обновлений от Telegram) ---
    # Используем try...finally для корректного завершения работы и закрытия ресурсов
    try:
        logger.info("Starting bot polling. Press Ctrl+C to stop.")
        # ЭТОТ ШАГ КРИТИЧЕСКИ ВАЖЕН ДЛЯ ИНЖЕКЦИИ ЗАВИСИМОСТЕЙ
        # Передаем НАШ подключенный экземпляр ProfileManager в start_polling
        # Aiogram увидит этот именованный аргумент и передаст его хэндлерам,
        # которые запросили аргумент с типом ProfileManager.
        await dp.start_polling(bot, profile_manager=profile_manager_instance)

    except KeyboardInterrupt:
        # Обработка остановки бота по Ctrl+C
        logger.info("Bot stopped manually (KeyboardInterrupt).")
    except Exception as e:
         # Логгирование любых других неожиданных ошибок во время поллинга
         logger.exception("Bot polling stopped with an unexpected error:")
    finally:
        # --- 7. Корректное завершение работы и закрытие ресурсов ---
        logger.info("Shutting down bot and closing database connection...")
        # Закрываем асинхронное соединение с БД (обязательно await)
        await profile_manager_instance.close()
        # Закрываем HTTP-сессию бота (обязательно await)
        await bot.session.close()
        logger.info("Shutdown complete.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user (KeyboardInterrupt/SystemExit)")
    except Exception as e:
        logger.critical(f"Fatal error in main execution: {e}", exc_info=True)

