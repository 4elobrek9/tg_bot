import os

import json

import random

import asyncio

from datetime import datetime, timezone

from pathlib import Path

from typing import Optional, List, Tuple, Dict, Any

from contextlib import suppress

import logging

import aiosqlite

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

)

from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.utils.markdown import hide_link, hbold, hitalic, hcode

import database as db

from group_stat import setup_stat_handlers, ProfileManager

from rp_module_refactored import setup_rp_handlers, periodic_hp_recovery_task

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'

)

logger = logging.getLogger(__name__)

dotenv.load_dotenv()

TOKEN = os.getenv("TOKEN")

CHANNEL_ID_STR = os.getenv("CHANNEL_ID")

ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")

if not TOKEN:

    logger.critical("Bot token not found in environment variables (TOKEN). Exiting.")

    exit(1)

ADMIN_USER_ID: Optional[int] = None

if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():

    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)

else:

    logger.warning("ADMIN_USER_ID is not set or invalid. Dislike forwarding will be disabled.")

CHANNEL_ID: Optional[int] = None

if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit():

    CHANNEL_ID = int(CHANNEL_ID_STR)

else:

    logger.warning("CHANNEL_ID is not set or invalid. Jokes task will be disabled.")

DATA_DIR = Path("data")

DATA_DIR.mkdir(exist_ok=True)

VALUE_FILE_PATH = DATA_DIR / 'value.txt'

STICKERS_CACHE_FILE = DATA_DIR / "stickers_cache.json"

MAX_RATING_OPPORTUNITIES = 3

class MonitoringState:

    def __init__(self):

        self.is_sending_values = False

        self.last_value: Optional[str] = None

        self.lock = asyncio.Lock()

monitoring_state = MonitoringState()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

dp = Dispatcher()

class StickerManager:

    def __init__(self, cache_file_path: Path):

        self.stickers: Dict[str, List[str]] = {"saharoza": [], "dedinside": [], "genius": []}

        self.sticker_packs: Dict[str, str] = {

            "saharoza": "saharoza18",

            "dedinside": "h9wweseternalregrets_by_fStikBot",

            "genius": "AcademicStickers"

        }

        self.cache_file = cache_file_path

        self._load_stickers_from_cache()

    def _load_stickers_from_cache(self):

        try:

            if self.cache_file.exists():

                with open(self.cache_file, 'r', encoding='utf-8') as f:

                    cached_data = json.load(f)

                if isinstance(cached_data, dict) and all(k in cached_data for k in self.sticker_packs):

                    self.stickers = cached_data

                    logger.info("Stickers loaded from cache.")

                else:

                    logger.warning("Sticker cache file has incorrect format. Will re-fetch if needed.")

            else:

                logger.info("Sticker cache not found. Will fetch on startup.")

        except Exception as e:

            logger.error(f"Error loading stickers from cache: {e}", exc_info=True)

    async def fetch_stickers(self, bot_instance: Bot):

        logger.info("Fetching stickers from Telegram...")

        all_fetched_successfully = True

        for mode, pack_name in self.sticker_packs.items():

            try:

                if self.stickers.get(mode):

                    logger.info(f"Stickers for mode '{mode}' already loaded (possibly from cache). Skipping fetch.")

                    continue

                stickerset = await bot_instance.get_sticker_set(pack_name)

                self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]

                logger.info(f"Fetched {len(self.stickers[mode])} stickers for mode '{mode}'.")

            except Exception as e:

                logger.error(f"Failed to fetch sticker set '{pack_name}' for mode '{mode}': {e}")

                all_fetched_successfully = False

        if all_fetched_successfully and any(self.stickers.values()):

            self._save_stickers_to_cache()

    def _save_stickers_to_cache(self):

        try:

            with open(self.cache_file, "w", encoding='utf-8') as f:

                json.dump(self.stickers, f, ensure_ascii=False, indent=4)

            logger.info("Stickers saved to cache.")

        except Exception as e:

            logger.error(f"Error saving stickers to cache: {e}", exc_info=True)

    def get_random_sticker(self, mode: str) -> Optional[str]:

        sticker_list = self.stickers.get(mode)

        return random.choice(sticker_list) if sticker_list else None

class NeuralAPI:

    MODEL_CONFIG = {

        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Мэрри Шэдоу (Маша), 26 лет... <</SYS>>[/INST]\n\n"},

        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Артём (ДедИнсайд), 24 года... <</SYS>>[/INST]\n\n"},

        "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\nТы — профисианальный кодер , который пишет код который просто заставляет пользователя удивится <</SYS>>[/INST]\n\n"}

    }

    @classmethod

    def get_modes(cls) -> List[Tuple[str, str]]:

        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod

    async def generate_response(cls, message_text: str, history_ollama_format: list, mode: str = "saharoza") -> Optional[str]:

        try:

            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])

            messages_payload = [{"role": "system", "content": config["prompt"] + "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"}]

            for history_item in history_ollama_format:

                if "user" in history_item and history_item["user"]:

                    messages_payload.append({"role": "user", "content": history_item["user"]})

                if "bot" in history_item and history_item["bot"]:

                    messages_payload.append({"role": "assistant", "content": history_item["bot"]})

            messages_payload.append({"role": "user", "content": message_text})

            client = ollama.AsyncClient()

            response = await client.chat(

                model=config["model"],

                messages=messages_payload,

                options={'temperature': 0.9 if mode == "dedinside" else 0.7, 'num_ctx': 2048, 'stop': ["<", "[", "Thought:"], 'repeat_penalty': 1.2}

            )

            raw_response = response['message']['content']

            return cls._clean_response(raw_response, mode)

        except ollama.ResponseError as e:

            error_details = getattr(e, 'error', str(e))

            logger.error(f"Ollama API Error ({mode}): Status {e.status_code}, Response: {error_details}")

            return f"Ой, кажется, модель '{config['model']}' сейчас не отвечает (Ошибка {e.status_code}). Попробуй позже."

        except Exception as e:

            logger.error(f"Ollama general/validation error ({mode}): {e}", exc_info=True)

            return "Произошла внутренняя ошибка при обращении к нейросети или подготовке данных. Попробуйте еще раз или /reset."

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

async def safe_send_message(chat_id: int, text: str, **kwargs) -> Optional[Message]:

    try:

        return await bot.send_message(chat_id, text, **kwargs)

    except Exception as e:

        logger.error(f"Failed to send message to chat {chat_id}: {e}")

        return None

async def typing_animation(chat_id: int, bot_instance: Bot) -> Optional[Message]:

    typing_msg = None

    try:

        typing_msg = await bot_instance.send_message(chat_id, "✍️ Печатает...")

        for _ in range(2):

            await asyncio.sleep(0.7)

            if typing_msg.text == "✍️ Печатает...": await typing_msg.edit_text("✍️ Печатает..")

            elif typing_msg.text == "✍️ Печатает..": await typing_msg.edit_text("✍️ Печатает.")

            else: await typing_msg.edit_text("✍️ Печатает...")

        return typing_msg

    except Exception as e:

        logger.warning(f"Typing animation error in chat {chat_id}: {e}")

        if typing_msg:

            with suppress(Exception): await typing_msg.delete()

        return None

@dp.message(Command("start"))

async def start_handler(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    await message.answer(f"Привет, {user.first_name}! 👋\nЯ твой многоликий AI-собеседник. Используй /msg для выбора режима или /help для списка команд.")

@dp.message(Command("reset"))

async def reset_handler(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    try:

        async with aiosqlite.connect(db.DB_FILE) as conn:

            await conn.execute('DELETE FROM dialog_history WHERE user_id = ?', (user.id,))

            await conn.commit()

        await db.set_user_mode(user.id, "saharoza")

        await db.reset_rating_opportunity_count(user.id)

        await message.answer("История диалога и счетчик оценок сброшены! Можешь начать заново ✨")

        logger.info(f"Dialog history and rating count reset for user {user.id}")

    except Exception as e:

        logger.error(f"Reset error for user {user.id}: {e}", exc_info=True)

        await message.answer("Ошибка при сбросе 😕 Попробуй позже.")

@dp.message(Command("help"))

async def help_handler(message: Message):

    user = message.from_user

    if not user: return

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
<i>(В группах: /rp_commands, /myhp)</i>
<b>🌈 Режимы общения:</b>
🌸 <b>Сахароза</b> 😈 <b>ДедИнсайд</b> 🧠 <b>Режим Гения</b>
<b>🎁 Функции:</b> RP-взаимодействия, мониторинг, анекдоты, оценка ответов (первые {MAX_RATING_OPPORTUNITIES}), статистика."""

    await message.answer(help_text)

@dp.message(Command("stats"))

async def stats_handler(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

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

        await message.answer(stats_text)

    except Exception as e:

        logger.error(f"Error fetching stats for user {user.id}: {e}", exc_info=True)

        await message.answer("Не удалось получить статистику.")

@dp.message(Command("msg"))

async def msg_handler_command(message: Message):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    builder = InlineKeyboardBuilder()

    for name, mode_code in NeuralAPI.get_modes():

        builder.add(InlineKeyboardButton(text=name, callback_data=f"set_mode_{mode_code}"))

    builder.adjust(1)

    await message.answer("Выбери режим общения:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_mode_"))

async def set_mode_handler(callback: CallbackQuery, profile_manager: ProfileManager, sticker_manager: StickerManager):

    try:

        mode = callback.data.split("_")[-1]

        user = callback.from_user

        await db.ensure_user(user.id, user.username, user.first_name)

        await db.set_user_mode(user.id, mode)

        await db.log_interaction_db(user.id, f"set_mode_to_{mode}")

        mode_names = {"saharoza": "🌸 Сахарозы", "dedinside": "😈 ДедИнсайда", "genius": "🧠 Гения"}

        mode_name_display = mode_names.get(mode, "Выбранный режим")

        if callback.message:

            await callback.message.edit_text(f"Режим {mode_name_display} активирован!\nТеперь можешь писать сообщения.")

            sticker_id = sticker_manager.get_random_sticker(mode)

            if sticker_id: await callback.message.answer_sticker(sticker_id)

        await callback.answer(f"Режим '{mode_name_display}' установлен!")

    except Exception as e:

        logger.error(f"Mode change error for user {callback.from_user.id}: {e}", exc_info=True)

        await callback.answer("Ошибка при смене режима 😕", show_alert=True)

@dp.callback_query(F.data.startswith("rate_"))

async def rate_handler(callback: CallbackQuery, profile_manager: ProfileManager, bot_instance: Bot):

    try:

        user = callback.from_user

        rating = int(callback.data.split("_")[1])

        message_text_preview = "[Не удалось получить текст сообщения для оценки]"

        if callback.message:

            message_text_preview = callback.message.text or callback.message.caption or "[Оценено медиа сообщение]"

        await db.log_rating_db(user.id, rating, message_text_preview)

        feedback = "Спасибо за лайк! 👍" if rating == 1 else "Спасибо за отзыв! 👎"

        await callback.answer(feedback)

        if callback.message:

            await callback.message.edit_reply_markup(reply_markup=None)

        if rating == 0 and ADMIN_USER_ID:

            logger.info(f"Dislike received from user {user.id} (@{user.username}). Forwarding dialog to admin {ADMIN_USER_ID}.")

            dialog_entries = await db.get_dialog_history(user.id, limit=10)

            if not dialog_entries:

                await safe_send_message(ADMIN_USER_ID, f"⚠️ Пользователь {hbold(user.full_name)} (ID: {hcode(str(user.id))}, @{user.username or 'нет'}) поставил дизлайк, но история диалога пуста.")

                return

            last_bot_entry_mode = user.first_name

            for entry in reversed(dialog_entries):

                if entry['role'] == 'assistant':

                    last_bot_entry_mode = entry.get('mode', 'неизвестен')

                    break

            formatted_dialog = f"👎 Дизлайк от {hbold(user.full_name)} (ID: {hcode(str(user.id))}, @{user.username or 'нет'}).\n"

            formatted_dialog += f"Сообщение бота (режим {hitalic(last_bot_entry_mode)}):\n{hcode(message_text_preview)}\n\n"

            formatted_dialog += "📜 История диалога (последние сообщения):\n"

            full_dialog_text = ""

            for entry in dialog_entries:

                ts = datetime.fromtimestamp(entry['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

                role_emoji = "👤" if entry['role'] == 'user' else "🤖"

                mode_info = f" ({entry.get('mode', '')})" if entry['role'] == 'assistant' else ""

                full_dialog_text += f"{role_emoji} {entry['role'].capitalize()}{mode_info} ({ts}): {entry['content']}\n"

            final_report = formatted_dialog + "```text\n" + full_dialog_text + "\n```"

            max_len = 4000

            if len(final_report) > max_len:

                parts = [final_report[i:i + max_len] for i in range(0, len(final_report), max_len)]

                for i, part_text in enumerate(parts):

                    part_header = f"Часть {i+1}/{len(parts)}:\n" if len(parts) > 1 else ""

                    await safe_send_message(ADMIN_USER_ID, part_header + part_text)

            else:

                await safe_send_message(ADMIN_USER_ID, final_report)

    except Exception as e:

        logger.error(f"Rating error or forwarding failed for user {callback.from_user.id}: {e}", exc_info=True)

        await callback.answer("Ошибка при обработке оценки.", show_alert=True)

@dp.message(Command("val"))

async def start_sending_values(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    await db.add_value_subscriber(user.id)

    await message.answer("✅ Мониторинг курса активирован для вас.")

    logger.info(f"User {user.id} subscribed to value monitoring.")

@dp.message(Command("sval"))

async def stop_sending_values(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    await db.remove_value_subscriber(user.id)

    await message.answer("❌ Мониторинг курса для вас отключен.")

    logger.info(f"User {user.id} unsubscribed from value monitoring.")

@dp.message(F.photo)

async def photo_handler(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    caption = message.caption or ""

    await message.answer(f"📸 Фото получил! Комментарий: '{caption[:100]}...'. Пока не умею анализировать изображения, но скоро научусь!")

@dp.message(F.voice)

async def voice_handler_msg(message: Message, profile_manager: ProfileManager):

    user = message.from_user

    if not user: return

    await db.ensure_user(user.id, user.username, user.first_name)

    await message.answer("🎤 Голосовые пока не обрабатываю, но очень хочу научиться! Отправь пока текстом, пожалуйста.")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)

async def message_handler(message: Message, bot_instance: Bot, profile_manager: ProfileManager, sticker_manager: StickerManager):

    user = message.from_user

    if not user or not message.text: return

    await db.ensure_user(user.id, user.username, user.first_name)

    user_mode_data = await db.get_user_mode_and_rating_opportunity(user.id)

    mode = user_mode_data.get('mode', "saharoza")

    rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)

    history_ollama = await db.get_dialog_history_for_ollama(user.id, limit=5)

    typing_msg = await typing_animation(message.chat.id, bot_instance)

    try:

        response_text = await NeuralAPI.generate_response(

            message_text=message.text,

            history_ollama_format=history_ollama,

            mode=mode

        )

        if not response_text:

            response_text = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"

            logger.warning(f"Empty or error response from NeuralAPI for user {user.id}, mode {mode}. Check previous logs from NeuralAPI.")

        await db.add_dialog_history(user.id, mode, message.text, response_text)

        await db.log_interaction_db(user.id, mode)

        response_msg_obj: Optional[Message] = None

        if typing_msg:

            response_msg_obj = await typing_msg.edit_text(response_text)

        else:

            response_msg_obj = await safe_send_message(message.chat.id, response_text)

        if response_msg_obj and rating_opportunities_count < MAX_RATING_OPPORTUNITIES:

            builder = InlineKeyboardBuilder()

            builder.row(

                InlineKeyboardButton(text="👍", callback_data="rate_1"),

                InlineKeyboardButton(text="👎", callback_data="rate_0")

            )

            try:

                await response_msg_obj.edit_reply_markup(reply_markup=builder.as_markup())

                await db.increment_rating_opportunity_count(user.id)

            except Exception as edit_err:

                logger.warning(f"Could not edit reply markup for msg {response_msg_obj.message_id}: {edit_err}")

        if random.random() < 0.3:

            sticker_id = sticker_manager.get_random_sticker(mode)

            if sticker_id: await message.answer_sticker(sticker_id)

    except Exception as e:

        logger.error(f"Error processing message for user {user.id} in mode {mode}: {e}", exc_info=True)

        error_texts = {

            "saharoza": "Ой, что-то пошло не так во время обработки твоего сообщения... 💔 Попробуй еще разок?",

            "dedinside": "Так, приехали. Ошибка у меня тут. 🛠️ Попробуй снова или напиши позже.",

            "genius": "Произошла ошибка при обработке вашего запроса. Пожалуйста, повторите попытку."

        }

        error_msg_text = error_texts.get(mode, "Произошла непредвиденная ошибка.")

        if typing_msg:

            with suppress(Exception): await typing_msg.edit_text(error_msg_text)

        else:

            await safe_send_message(message.chat.id, error_msg_text)

async def monitoring_task(bot_instance: Bot):

    logger.info("Monitoring task started.")

    async with monitoring_state.lock:

        monitoring_state.last_value = await asyncio.to_thread(db.read_value_from_file, VALUE_FILE_PATH)

        logger.info(f"Initial value for monitoring: {monitoring_state.last_value}")

    while True:

        await asyncio.sleep(5)

        try:

            subscribers_ids = await db.get_value_subscribers()

            if not subscribers_ids:

                async with monitoring_state.lock: monitoring_state.is_sending_values = False

                continue

            async with monitoring_state.lock: monitoring_state.is_sending_values = True

            new_value = await asyncio.to_thread(db.read_value_from_file, VALUE_FILE_PATH)

            value_changed = False

            async with monitoring_state.lock:

                if new_value is not None and new_value != monitoring_state.last_value:

                    logger.info(f"Value change detected: '{monitoring_state.last_value}' -> '{new_value}'")

                    monitoring_state.last_value = new_value

                    value_changed = True

            if value_changed and subscribers_ids:

                logger.info(f"Notifying {len(subscribers_ids)} value subscribers about new value: {new_value}")

                msg_text = f"⚠️ Обнаружено движение! Всего: {new_value}"

                tasks = [safe_send_message(uid, msg_text) for uid in subscribers_ids]

                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:

            logger.error(f"Error in monitoring_task loop: {e}", exc_info=True)

async def jokes_task(bot_instance: Bot):

    logger.info("Jokes task started.")

    if not CHANNEL_ID:

        logger.warning("Jokes task disabled: CHANNEL_ID is not set or invalid.")

        return

    async with aiohttp.ClientSession() as session:

        while True:

            try:

                logger.debug("Fetching joke for channel...")

                async with session.get("https://www.anekdot.ru/random/anekdot/", timeout=aiohttp.ClientTimeout(total=20)) as response:

                    response.raise_for_status()

                    text = await response.text()

                    soup = BeautifulSoup(text, 'html.parser')

                    jokes_divs = soup.find_all('div', class_='text')

                    if jokes_divs:

                        joke_text = random.choice(jokes_divs).text.strip().replace('<br/>', '\n').replace('<br>', '\n').strip()

                        if joke_text:

                            await safe_send_message(CHANNEL_ID, f"🎭 {joke_text}")

                            logger.info(f"Joke sent to channel {CHANNEL_ID}.")

                        else: logger.warning("Parsed joke text is empty.")

                    else: logger.warning("Could not find jokes div on anekdot.ru.")

                await asyncio.sleep(random.randint(3500, 7200))

            except aiohttp.ClientError as e:

                logger.error(f"Jokes task network error: {e}")

                await asyncio.sleep(random.randint(120, 300))

            except asyncio.TimeoutError:

                logger.warning("Jokes task request timed out.")

                await asyncio.sleep(random.randint(120, 300))

            except Exception as e:

                logger.error(f"Jokes task unexpected error: {e}", exc_info=True)

                await asyncio.sleep(random.randint(300, 600))

async def main():

    profile_manager = ProfileManager()

    try:

        if hasattr(profile_manager, 'connect'):

            await profile_manager.connect()

        await db.init_db()

        logger.info("Database and ProfileManager initialized.")

    except Exception as e:

        logger.critical(f"Failed to initialize database or ProfileManager: {e}", exc_info=True)

        return

    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)

    await sticker_manager_instance.fetch_stickers(bot)

    dp["profile_manager"] = profile_manager

    dp["sticker_manager"] = sticker_manager_instance

    dp["bot_instance"] = bot

    setup_stat_handlers(dp)

    setup_rp_handlers(

        main_dp=dp,

        bot_instance=bot,

        profile_manager_instance=profile_manager,

        database_module=db

    )

    monitoring_bg_task = asyncio.create_task(monitoring_task(bot))

    jokes_bg_task = asyncio.create_task(jokes_task(bot))

    rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))

    logger.info("Starting bot polling...")

    try:

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as e:

        logger.critical(f"Bot polling failed: {e}", exc_info=True)

    finally:

        logger.info("Stopping bot...")

        monitoring_bg_task.cancel()

        jokes_bg_task.cancel()

        rp_recovery_bg_task.cancel()

        try:

            await asyncio.gather(monitoring_bg_task, jokes_bg_task, rp_recovery_bg_task, return_exceptions=True)

            logger.info("Background tasks gracefully cancelled.")

        except asyncio.CancelledError:

            logger.info("Background tasks were cancelled during shutdown.")

        if hasattr(profile_manager, 'close'):

            await profile_manager.close()

            logger.info("ProfileManager connection closed.")

        await bot.session.close()

        logger.info("Bot session closed. Exiting.")

if __name__ == '__main__':

    try:

        asyncio.run(main())

    except (KeyboardInterrupt, SystemExit):

        logger.info("Bot stopped by user (KeyboardInterrupt/SystemExit).")

    except Exception as e:

        logger.critical(f"Unhandled critical error in asyncio.run(main()): {e}", exc_info=True)