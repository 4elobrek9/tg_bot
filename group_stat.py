# import asyncio # Не нужен в модуле, если только для внутримодульных async задач, но для хэндлеров и ProfileManager не нужен
import os
import aiosqlite
import string
import sqlite3 # Только для синхронной init_db
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional, Dict, Any
from aiogram import Dispatcher, types, Bot # Bot не нужен здесь, только в главном скрипте
from aiogram.filters import Command
import logging
# Настройка логгирования должна быть в главном файле, здесь просто получаем логгер
logger = logging.getLogger(__name__)

from PIL import Image, ImageDraw, ImageFont
import requests
from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.types import BufferedInputFile
# Command и F уже импортированы выше
# from aiogram.filters import Command
# from aiogram import F
import random
import aiohttp
# dotenv не нужен в модуле, загружается в главном скрипте
# from dotenv import load_dotenv

formatter = string.Formatter()

stat_router = Router(name="stat_router")

# Конфигурация
class ProfileConfig:
    DEFAULT_BG_URL = "https://images.steamusercontent.com/ugc/2109432979738958246/80A8B1D46BC2434A53C634DE9721205228BEA966/"
    FONT_PATH = "Hlobus.ttf"  # Ваш пользовательский шрифт (убедитесь, что файл существует рядом или укажите полный путь!)
    TEXT_COLOR = (255, 255, 255)  # Белый цвет текста
    TEXT_SHADOW = (0, 0, 0)  # Черная тень
    MARGIN = 15  # Отступ от краев
    AVATAR_SIZE = 50
    AVATAR_OFFSET = (MARGIN, MARGIN)
    USER_ID_OFFSET = (MARGIN + AVATAR_SIZE + 10, MARGIN + 5) # Смещение для User ID
    EXP_BAR_OFFSET = (MARGIN, MARGIN + AVATAR_SIZE + 10) # Смещение для шкалы опыта
    MONEY_OFFSET_RIGHT = 15 # Отступ денег справа
    HP_OFFSET = (MARGIN, MARGIN + AVATAR_SIZE + 35) # Смещение для HP (перенесено ниже exp bar)

    FLAMES_OFFSET_X = -70 # Офсет справа (от края картинки)
    FLAMES_OFFSET_Y = MARGIN

    MESSAGES_OFFSET_X = -100 # Офсет справа (от края картинки)
    MESSAGES_OFFSET_Y = MARGIN + 25 # Ниже Flames

    HP_COLORS = {
        "high": (0, 128, 0),      # Зеленый
        "medium": (255, 165, 0),  # Оранжевый
        "low": (255, 0, 0),      # Красный
        "very_high": (255, 69, 0) # Красный огонь (возможно, для очень низкого HP?)
    }
    MAX_HP = 150
    MAX_LEVEL = 169
    EXP_PER_MESSAGE_INTERVAL = 10 # Каждые 10 сообщений +1 EXP
    EXP_AMOUNT_PER_INTERVAL = 1

    LUMCOINS_PER_LEVEL = {
        1: 1, 10: 2, 20: 3, 30: 5,
        50: 8, 100: 15, 150: 25, 169: 50
    }
    WORK_REWARD_MIN = 5
    WORK_REWARD_MAX = 20
    WORK_COOLDOWN_SECONDS = 15 * 60 # 15 минут в секундах
    WORK_TASKS = [
        "чистил(а) ботинки",
        "поливал(а) цветы",
        "ловил(а) бабочек",
        "собирал(а) ягоды",
        "помогал(а) старушке перейти дорогу",
        "писал(а) стихи",
        "играл(а) на гитаре",
        "готовил(а) обед",
        "читал(а) книгу",
        "смотрел(а) в окно"
    ]
    BACKGROUND_SHOP = {
        "space": {"name": "Космос", "url": "https://images.unsplash.com/photo-1506318137072-291786a88698?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8M3x8c3BhY2V8ZW58MHx8MHx8fDA%3D&auto=format&fit=crop&w=500&q=60", "cost": 50},
        "nature": {"name": "Природа", "url": "https://images.unsplash.com/photo-1440330559787-852571c1c71a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTB8fG5hdHVyZXxlbnwwfHwwfHww&auto=format&fit=crop&w=500&q=60", "cost": 40},
        "city": {"name": "Город", "url": "https://images.unsplash.com/photo-1519013876546-8858ba07e532?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTJ8fGNpdHl8ZW58MHx8MHx8fDA%3D&auto=format&fit=crop&w=500&q=60", "cost": 60},
        "abstract": {"name": "Абстракция", "url": "https://images.unsplash.com/photo-1508768787810-6adc1f09aeda?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8N3x8YWJzdHJhY3R8ZW58MHx8MHx8fDA%3D&auto=format&fit=crop&w=500&q=60", "cost": 30}
    }
    FONT_SIZE_LARGE = 24
    FONT_SIZE_MEDIUM = 20
    FONT_SIZE_SMALL = 16

# Инициализация базы данных (синхронная для старта - ОСТАВЛЯЕМ ДЛЯ ПЕРВОГО ЗАПУСКА)
# Это гарантирует создание файла и таблиц, если их нет, перед тем как aiosqlite попытается подключиться.
def init_db():
    if not os.path.exists('profiles.db'):
        conn = sqlite3.connect('profiles.db') # Используем sync sqlite3 for initial setup
        cursor = conn.cursor()

        # Ваши CREATE TABLE запросы...
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
            level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
            exp INTEGER DEFAULT 0,
            lumcoins INTEGER DEFAULT 0,
            daily_messages INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            flames INTEGER DEFAULT 0,
            background_url TEXT,
            last_work_time REAL DEFAULT 0, -- Добавляем поле для кулдауна работы
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS backgrounds (
            user_id INTEGER PRIMARY KEY,
            background_url TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        conn.commit()
        conn.close()
        logger.info("Database initialized (sync).")
    else:
        logger.info("Database already exists (sync check).")

# Запускаем синхронную инициализацию при загрузке скрипта
init_db()


class ProfileManager:
    def __init__(self):
        self._conn = None # Инициализируем соединение как None
        self.font_cache = {} # Оставляем кэш шрифтов
        logger.info("ProfileManager instance created.")

    async def connect(self):
        """Устанавливает асинхронное соединение с базой данных и инициализирует схему."""
        if self._conn is not None:
            logger.warning("Database connection already exists.")
            return

        logger.info("Connecting to database...")
        try:
            # Устанавливаем соединение aiosqlite
            # check_same_thread=False может потребоваться, если вы используете
            # соединение в разных потоках (что нежелательно в async/await),
            # но для одного event loop'а это обычно не нужно.
            # Оставляем по умолчанию (True) для безопасности.
            self._conn = await aiosqlite.connect('profiles.db')
            # Можно добавить изоляцию, если нужно, например:
            # self._conn.isolation_level = None # Автоматический коммит, или управлять вручную

            logger.info("Database connected asynchronously.")

            # Асинхронная инициализация (повторно, на случай если sync init не сработал или таблицы добавлены позже)
            await self._init_db_async()
            logger.info("Database schema checked/initialized asynchronously.")

        except Exception as e:
            logger.exception("Failed to connect to database or initialize schema:")
            # Важно: если соединение не установилось, self._conn останется None.
            # Это вызовет Runtime Error в хэндлерах, что правильно.
            raise # Перевыбрасываем исключение, чтобы бот не стартовал без БД

    async def close(self):
        """Закрывает асинхронное соединение с базой данных."""
        if self._conn is not None:
            logger.info("Closing database connection...")
            try:
                await self._conn.close()
                self._conn = None
                logger.info("Database connection closed.")
            except Exception as e:
                logger.exception("Error closing database connection:")

    # Эта асинхронная инициализация гарантирует создание таблиц,
    # даже если init_db() не была запущена или новые таблицы добавлены.
    async def _init_db_async(self):
        """Асинхронная инициализация (создание таблиц), если их нет."""
        if self._conn is None:
             logger.error("Cannot perform async DB init: connection is None.")
             return # Или поднять ошибку, в зависимости от логики

        cursor = await self._conn.cursor()

        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
            level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
            exp INTEGER DEFAULT 0,
            lumcoins INTEGER DEFAULT 0,
            daily_messages INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            flames INTEGER DEFAULT 0,
            background_url TEXT,
            last_work_time REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS backgrounds (
            user_id INTEGER PRIMARY KEY,
            background_url TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        await cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        await self._conn.commit() # Коммитим изменения после создания таблиц


    async def _get_or_create_user(self, user: types.User) -> int:
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ''', (user.id, user.username, user.first_name, user.last_name))
        await self._conn.commit()
        return user.id

    async def _get_or_create_profile(self, user_id: int) -> Dict[str, Any]:
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
        await self._conn.commit()

        await cursor.execute('''
        SELECT * FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile = await cursor.fetchone()

        if not profile:
            return None

        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, profile))

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        """Получает или создает профиль пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()

        # Создаем или обновляем пользователя в таблице users
        await cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name
        ''', (user.id, user.username, user.first_name, user.last_name))
        # Используем INSERT OR REPLACE для создания/обновления фона, если он не существует
        # await cursor.execute('''
        # INSERT OR IGNORE INTO backgrounds (user_id, background_url)
        # VALUES (?, ?)
        # ''', (user.id, ProfileConfig.DEFAULT_BG_URL)) # Это можно убрать, фон хранится в user_profiles по умолчанию

        await self._conn.commit() # Коммитим изменения в users

        user_id = user.id

        # Создаем профиль в user_profiles, если его нет
        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
        await self._conn.commit() # Коммитим создание профиля

        # Получаем данные профиля из user_profiles
        await cursor.execute('''
        SELECT * FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile = await cursor.fetchone()

        if not profile:
            logger.error(f"Profile not found for user_id {user_id} after creation attempt.")
            return None

        columns = [column[0] for column in cursor.description]
        profile_data = dict(zip(columns, profile))

        # Получаем данные пользователя (никнейм) из users
        # (Хотя мы только что обновили/создали его, лучше получить актуальные данные)
        await cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
        user_data = await cursor.fetchone()

        if user_data:
             # Предпочитаем username, если есть, иначе first_name
             profile_data['username'] = f"@{user_data[0]}" if user_data[0] else user_data[1]
        else:
             # Fallback if user somehow exists without a user record (unlikely with INSERT OR IGNORE/REPLACE)
             profile_data['username'] = user.first_name # Or some default

        # Получаем кастомный фон из backgrounds
        await cursor.execute('SELECT background_url FROM backgrounds WHERE user_id = ?', (user_id,))
        custom_bg = await cursor.fetchone()
        if custom_bg:
            profile_data['background_url'] = custom_bg[0] # Используем кастомный фон, если он есть
        else:
            # Если кастомного нет в таблице backgrounds, используем фон из user_profiles
            # который либо DEFAULT_BG_URL при создании, либо был установлен ранее
            # через set_background (который обновляет таблицу backgrounds).
            # Таким образом, фоном по умолчанию будет поле background_url из user_profiles,
            # а если в backgrounds есть запись для юзера, то фон оттуда.
            # Ваша логика set_background пишет в backgrounds, а не в user_profiles,
            # поэтому получение фона из backgrounds - правильный подход.
            # Строка ниже уже не нужна, т.к. profile_data['background_url'] уже содержит
            # значение из user_profiles, если в backgrounds ничего не найдено.
            # profile_data['background_url'] = profile_data.get('background_url', ProfileConfig.DEFAULT_BG_URL)
            pass # Значение уже установлено из user_profiles


        return profile_data


    async def record_message(self, user: types.User) -> None:
        """Записывает активность сообщения, обновляет счетчики, опыт и уровень."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        user_id = user.id

        # Получаем текущие данные
        await cursor.execute('''
        SELECT total_messages, level, exp, lumcoins
        FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile_data = await cursor.fetchone()

        if not profile_data:
             logger.error(f"Profile not found for user_id: {user_id} in record_message. Skipping message count.")
             return # Не можем обновить, если профиля нет (должен быть создан get_user_profile)

        total_messages, level, exp, lumcoins = profile_data

        total_messages += 1
        daily_messages_increment = 1

        exp_added = 0

        # Проверяем, нужно ли начислять опыт за сообщение
        # Начисляем EXP только если новое total_messages является кратным
        # и предыдущее total_messages было меньше этого кратного.
        # Например, если EXP начисляется каждые 10 сообщений:
        # prev_total = 9, current_total = 10 -> начисляем
        # prev_total = 10, current_total = 11 -> не начисляем
        # prev_total = 19, current_total = 20 -> начисляем
        # prev_total = 20, current_total = 21 -> не начисляем
        # Это можно сделать, сравнивая целочисленное деление на интервал.
        # Если (total_messages // EXP_PER_MESSAGE_INTERVAL) > ( (total_messages - 1) // EXP_PER_MESSAGE_INTERVAL )
        # Это условие истинно только когда total_messages становится кратным EXP_PER_MESSAGE_INTERVAL
        # и предыдущее значение не было кратным.
        if total_messages > 0 and total_messages % ProfileConfig.EXP_PER_MESSAGE_INTERVAL == 0:
             # Проверяем, что опыт уже не был начислен за это "окно"
             # Это более точное условие: total_messages // 10 != (total_messages - 1) // 10
             # Но для простоты и совместимости с вашим кодом, оставлю проверку только на кратность.
             # Если вам нужно гарантировать, что опыт начисляется строго один раз за интервал,
             # нужно хранить в БД поле last_exp_message_count и сравнивать с ним.
             # Оставляем по простому условию % 10 == 0, как было в вашем коде.
             # Если total_messages=10, (10 % 10 == 0) True. Exp += 1.
             # Если total_messages=20, (20 % 10 == 0) True. Exp += 1.
             # Этот подход может начислять опыт повторно, если бот перезапускался между сообщениями.
             # Более надежно: хранить в БД поле 'last_exp_messages_chunk' (например, total_messages // 10)
             # и начислять опыт, если (total_messages // 10) > last_exp_messages_chunk.
             # Но давайте пока оставим вашу текущую логику:
             exp_added = ProfileConfig.EXP_AMOUNT_PER_INTERVAL


        new_exp = exp + exp_added
        new_level = level
        new_lumcoins = lumcoins # Изначально монеты не меняются здесь от уровня

        # Проверяем возможность повышения уровня и начисляем монеты за уровень
        # Пока новый опыт больше или равен необходимому для текущего уровня И уровень не максимальный
        while new_exp >= self._get_exp_for_level(new_level) and new_level < ProfileConfig.MAX_LEVEL:
             needed_for_current = self._get_exp_for_level(new_level)
             new_exp -= needed_for_current # Вычитаем опыт, нужный для текущего уровня
             new_level += 1 # Увеличиваем уровень
             # Награда начисляется ЗА НОВЫЙ уровень
             coins_this_level = self._get_lumcoins_for_level(new_level)
             new_lumcoins += coins_this_level # Добавляем монеты за достигнутый уровень
             # needed_exp = self._get_exp_for_level(new_level) # Обновляем необходимое EXP для нового уровня


        # Обновляем профиль
        await cursor.execute('''
        UPDATE user_profiles
        SET daily_messages = daily_messages + ?,
            total_messages = ?,
            exp = ?,
            level = ?,
            lumcoins = ?
        WHERE user_id = ?
        ''', (daily_messages_increment, total_messages, new_exp, new_level, new_lumcoins, user_id))
        await self._conn.commit()

        # Эта функция теперь только обновляет БД.
        # Проверку на повышение уровня и отправку сообщения
        # будем делать в хэндлере track_message_activity после вызова record_message.


    def _get_exp_for_level(self, level: int) -> int:
        """Возвращает количество опыта, необходимое для достижения УРОВНЯ `level`
           (т.е. кап опыта на уровне `level-1` для перехода на уровень `level`).
           Если уровень 1, возвращает EXP для перехода на уровень 2.
        """
        if level < 1:
            return 0 # Невозможно достичь уровня < 1

        # Если level = 1, нужно EXP для перехода на уровень 2.
        # Используем формулу для N = level + 1 (следующий уровень).
        # Или, как в вашем коде, считаем, что нужно X опыта *находясь на* уровне L,
        # чтобы перейти на L+1. Ваша формула выглядит так:
        base_exp = 100
        coefficient = 2
        multiplier = 5
        # Оставим вашу формулу: exp, необходимый для перехода *с* уровня `level` *на* `level + 1`
        # То есть, если у вас level, нужно накопить `base_exp + (level ** coefficient) * multiplier` опыта,
        # чтобы перейти на level + 1.
        return base_exp + (level ** coefficient) * multiplier


    def _get_lumcoins_for_level(self, level: int) -> int:
        """Возвращает награду LUMcoins за достижение УРОВНЯ `level`."""
        for lvl, coins in sorted(ProfileConfig.LUMCOINS_PER_LEVEL.items(), reverse=True):
            if level >= lvl:
                return coins
        return 1 # Награда по умолчанию для низких уровней (уровень 1)


    async def generate_profile_image(self, user: types.User, profile: Dict[str, Any]) -> BytesIO:
            """Генерирует изображение профиля пользователя."""
            # Убедитесь, что локальные переменные для размеров полосы опыта определены
            exp_bar_width = 250
            exp_bar_height = 30

            # --- Загрузка и кеширование шрифтов ---
            # Проверка существования файла шрифта
            if not os.path.exists(ProfileConfig.FONT_PATH):
                logger.error(f"Font file not found: {ProfileConfig.FONT_PATH}. Using default font.")
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            else:
                # Используйте кеш шрифтов
                if ProfileConfig.FONT_PATH not in self.font_cache:
                    try:
                        # Пытаемся загрузить шрифты разных размеров
                        self.font_cache[ProfileConfig.FONT_PATH] = {
                                'large': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_LARGE),
                                'medium': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_MEDIUM),
                                'small': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_SMALL)
                        }
                        logger.info(f"Font '{ProfileConfig.FONT_PATH}' loaded successfully.")
                    except Exception as e:
                        # Если загрузка шрифта не удалась (например, файл поврежден)
                        logger.exception(f"Failed to load font '{ProfileConfig.FONT_PATH}':")
                        # Используем шрифты по умолчанию как запасной вариант
                        font_large = ImageFont.load_default()
                        font_medium = ImageFont.load_default()
                        font_small = ImageFont.load_default()
                # Получаем шрифты из кеша или используем запасные
                font_large = self.font_cache[ProfileConfig.FONT_PATH].get('large', ImageFont.load_default())
                font_medium = self.font_cache[ProfileConfig.FONT_PATH].get('medium', ImageFont.load_default())
                font_small = self.font_cache[ProfileConfig.FONT_PATH].get('small', ImageFont.load_default())


            # --- Получение URL фона и аватара ---
            bg_url = profile.get('background_url', ProfileConfig.DEFAULT_BG_URL)
            # avatar_url = user.photo.big_file_id if user.photo else None
            # Примечание: Получение самой аватарки требует объекта bot и его async методов (get_file, download_file),
            # которые недоступны напрямую в этом методе ProfileManager.
            # Загрузка аватарки здесь пока пропущена. Если она нужна, придется передавать file_id
            # или BytesIO аватарки в этот метод из хэндлера show_profile, где есть доступ к bot.


            # --- Генерация изображения ---
            try:
                # Загрузка фона по URL
                async with aiohttp.ClientSession() as session:
                    async with session.get(bg_url) as resp:
                        resp.raise_for_status() # Проверка на ошибки HTTP (404, 500 и т.д.)
                        bg_image_data = await resp.read()
                bg_image = Image.open(BytesIO(bg_image_data)).convert("RGBA")
                bg_image = bg_image.resize((600, 200)) # Примерный размер профиля (можно сделать настраиваемым)

                # Создание прозрачного слоя для текста и элементов поверх фона
                overlay = Image.new('RGBA', bg_image.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                # --- Загрузка и наложение аватарки (Пропущено, см. комментарий выше) ---
                # avatar_image = None
                # ... (код загрузки и наложения аватара, если реализовано) ...


                # --- Получение данных профиля из словаря ---
                level = profile.get('level', 1)
                exp = profile.get('exp', 0)
                lumcoins = profile.get('lumcoins', 0)
                hp = profile.get('hp', 100)
                total_messages = profile.get('total_messages', 0)
                flames = profile.get('flames', 0)
                # Используем username, полученный в get_user_profile, или fallback на first_name
                username = profile.get('username', user.first_name)

                # --- Форматирование текста для изображения ---
                user_info_text = f"{username}"
                level_text = f"Уровень: {level}"
                # Показываем текущий опыт И сколько нужно для следующего уровня (если не максимальный)
                needed_exp_for_next_level = self._get_exp_for_level(level)
                if level < ProfileConfig.MAX_LEVEL:
                    # Убеждаемся, что опыт для отображения не превышает максимальный для уровня
                    display_exp = min(exp, needed_exp_for_next_level) if needed_exp_for_next_level > 0 else exp
                    exp_text = f"Опыт: {display_exp} / {needed_exp_for_next_level}"
                else:
                    exp_text = f"Опыт: {exp} (МАКС)" # Если максимальный уровень

                money_text = f"💎 {lumcoins}"
                hp_text = f"❤️ HP: {hp}/{ProfileConfig.MAX_HP}"
                flames_text = f"🔥 {flames}"
                messages_text = f"✉️ {total_messages}"


                # --- Вспомогательная функция для рисования текста с тенью ---
                def draw_text_with_shadow(draw_obj, position, text, font, text_color, shadow_color, shadow_offset=(1, 1)):
                    shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
                    draw_obj.text(shadow_pos, text, font=font, fill=shadow_color)
                    draw_obj.text(position, text, font=font, fill=text_color)


                # --- Отрисовка элементов на оверлее ---

                # User ID/Username (Располагаем справа от возможной аватарки)
                username_pos = (ProfileConfig.AVATAR_OFFSET[0] + ProfileConfig.AVATAR_SIZE + 10, ProfileConfig.AVATAR_OFFSET[1] + 5)
                draw_text_with_shadow(draw, username_pos, user_info_text, font_large, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)

                # Уровень (Ниже юзернейма)
                # Рассчитываем позицию на основе размера текста юзернейма и отступа
                username_bbox = draw.textbbox((0,0), user_info_text, font=font_large)
                username_height = username_bbox[3] - username_bbox[1]
                level_pos_y = username_pos[1] + username_height + 5 # Отступ 5px
                level_pos = (username_pos[0], level_pos_y)
                draw_text_with_shadow(draw, level_pos, level_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)

                # HP (Ниже уровня, но слева, рядом с EXP баром)
                # Рассчитываем позицию HP ниже EXP бара
                # --- ИСПРАВЛЕНАЯ СТРОКА ИСПОЛЬЗУЕТ exp_bar_height ---
                hp_pos_y = ProfileConfig.EXP_BAR_OFFSET[1] + exp_bar_height + 5 # Используем локальную переменную exp_bar_height + 5px отступ
                hp_pos = (ProfileConfig.EXP_BAR_OFFSET[0], hp_pos_y)
                # Определяем цвет HP в зависимости от значения
                hp_color = ProfileConfig.HP_COLORS.get("high") # Цвет по умолчанию высокий
                if hp < ProfileConfig.MAX_HP * 0.2 and hp > 0: # Менее 20% (и не 0)
                    hp_color = ProfileConfig.HP_COLORS.get("low", hp_color)
                elif hp < ProfileConfig.MAX_HP * 0.5 and hp > 0: # Менее 50% (и не 0)
                    hp_color = ProfileConfig.HP_COLORS.get("medium", hp_color)
                elif hp == 0:
                    hp_color = ProfileConfig.HP_COLORS.get("low", (128, 0, 0)) # Темно-красный или красный
                # Отрисовка HP текста с выбранным цветом
                draw_text_with_shadow(draw, hp_pos, hp_text, font_medium, hp_color, ProfileConfig.TEXT_SHADOW)


                # Опыт (Exp) - Шкала
                # exp_bar_width = 200 # Уже определено выше
                # exp_bar_height = 10 # Уже определено выше
                # Используем смещение из конфига
                exp_bar_pos = ProfileConfig.EXP_BAR_OFFSET

                # Рассчитываем процент заполнения полосы опыта
                needed_exp_for_next_level = self._get_exp_for_level(level)
                # Процент заполнения: текущий опыт / опыт до следующего уровня
                # Если максимальный уровень или нужный опыт 0, считаем 100%
                current_exp_percentage = 0.0
                if level < ProfileConfig.MAX_LEVEL and needed_exp_for_next_level > 0:
                    current_exp_percentage = min(exp / needed_exp_for_next_level, 1.0) # Не больше 100%
                elif level == ProfileConfig.MAX_LEVEL:
                    current_exp_percentage = 1.0 # На максимальном уровне полоса всегда полная

                exp_bar_fill_width = int(exp_bar_width * current_exp_percentage)

                # Фон шкалы опыта (серый полупрозрачный)
                draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_width, exp_bar_pos[1] + exp_bar_height)], fill=(50, 50, 50, 128))

                # Заполненная часть шкалы опыта (зеленая полупрозрачная)
                if exp_bar_fill_width > 0:
                    draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_fill_width, exp_bar_pos[1] + exp_bar_height)], fill=(0, 255, 0, 192))

                # Текст опыта над шкалой
                # Получаем размер текста exp_text
                exp_text_bbox = draw.textbbox((0,0), exp_text, font=font_small)
                exp_text_height = exp_text_bbox[3] - exp_text_bbox[1]
                # Рассчитываем позицию текста опыта над шкалой
                exp_text_pos_x = exp_bar_pos[0] # Выравниваем по левому краю шкалы
                exp_text_pos_y = exp_bar_pos[1] - exp_text_height - 2 # 2px отступ над шкалой
                draw_text_with_shadow(draw, (exp_text_pos_x, exp_text_pos_y), exp_text, font_small, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)


                # Lumcoins (справа вверху)
                money_text_bbox = draw.textbbox((0,0), money_text, font=font_medium)
                money_text_width = money_text_bbox[2] - money_text_bbox[0]
                money_pos_x = bg_image.size[0] - ProfileConfig.MONEY_OFFSET_RIGHT - money_text_width
                money_pos_y = ProfileConfig.MARGIN
                draw_text_with_shadow(draw, (money_pos_x, money_pos_y), money_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)

                # Flames (справа, ниже Lumcoins)
                flames_text_bbox = draw.textbbox((0,0), flames_text, font=font_medium)
                flames_text_width = flames_text_bbox[2] - flames_text_bbox[0]
                flames_text_height = flames_text_bbox[3] - flames_text_bbox[1]
                flames_pos_x = bg_image.size[0] + ProfileConfig.FLAMES_OFFSET_X - flames_text_width # Офсет уже отрицательный
                flames_pos_y = ProfileConfig.FLAMES_OFFSET_Y + (money_text_bbox[3] - money_text_bbox[1]) + 5 # Отступ от денег + 5px
                draw_text_with_shadow(draw, (flames_pos_x, flames_pos_y), flames_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)

                # Messages (справа, ниже Flames)
                messages_text_bbox = draw.textbbox((0,0), messages_text, font=font_medium)
                messages_text_width = messages_text_bbox[2] - messages_text_bbox[0]
                # messages_text_height = messages_text_bbox[3] - messages_text_bbox[1] # Не используется для позиции
                messages_pos_x = bg_image.size[0] + ProfileConfig.MESSAGES_OFFSET_X - messages_text_width # Офсет уже отрицательный
                messages_pos_y = ProfileConfig.MESSAGES_OFFSET_Y + flames_text_height + 5 # Отступ от огней + 5px
                draw_text_with_shadow(draw, (messages_pos_x, messages_pos_y), messages_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)


                # --- Наложение оверлея на фон ---
                composite = Image.alpha_composite(bg_image, overlay)

                # --- Сохранение в BytesIO ---
                byte_io = BytesIO()
                composite.save(byte_io, format='PNG')
                byte_io.seek(0) # Перематываем курсор в начало потока
                return byte_io

            except Exception as e:
                logger.exception("Error generating profile image:")
                # --- Fallback: Создание изображения с ошибкой ---
                try:
                    error_img = Image.new('RGB', (600, 200), color = (255, 0, 0)) # Красный фон
                    d = ImageDraw.Draw(error_img)
                    # Попробуем загрузить шрифт по умолчанию, если Hlobus не найден или поврежден
                    try:
                        error_font = ImageFont.truetype(ProfileConfig.FONT_PATH, 30)
                    except:
                        error_font = ImageFont.load_default() # Запасной шрифт

                    text = "Ошибка при загрузке/генерации профиля"
                    # Центрируем текст ошибки
                    text_bbox = d.textbbox((0,0), text, font=error_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = (600 - text_width) // 2
                    text_y = (200 - text_height) // 2
                    d.text((text_x, text_y), text, fill=(255,255,255), font=error_font) # Белый текст ошибки

                    byte_io = BytesIO()
                    error_img.save(byte_io, format='PNG')
                    byte_io.seek(0)
                    return byte_io
                except Exception as fallback_e:
                    logger.exception("Failed to generate error image fallback:")
                    # Если даже fallback не сработал, возвращаем пустой BytesIO
                    return BytesIO()
        
    async def update_lumcoins(self, user_id: int, amount: int):
        """Обновляет количество LUMcoins пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET lumcoins = lumcoins + ?
        WHERE user_id = ?
        ''', (amount, user_id))
        await self._conn.commit()

    async def get_lumcoins(self, user_id: int) -> int:
        """Получает количество LUMcoins пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT lumcoins FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0 # Возвращаем 0, если профиля нет (хотя get_user_profile должен его создать)

    async def set_background(self, user_id: int, background_url: str):
        """Устанавливает URL кастомного фона для пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        # Используем INSERT OR REPLACE для добавления или обновления фона пользователя в таблице backgrounds
        await cursor.execute('''
        INSERT OR REPLACE INTO backgrounds (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, background_url))
        await self._conn.commit()

    def get_available_backgrounds(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает словарь доступных фонов из конфига."""
        return ProfileConfig.BACKGROUND_SHOP

    async def get_last_work_time(self, user_id: int) -> float:
        """Получает время последней работы пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT last_work_time FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0.0 # Возвращаем 0.0 если нет данных (никогда не работал)

    async def update_last_work_time(self, user_id: int, timestamp: float):
        """Обновляет время последней работы пользователя."""
        if self._conn is None: raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET last_work_time = ?
        WHERE user_id = ?
        ''', (timestamp, user_id))
        await self._conn.commit()

# --- Хэндлеры ---
# Все хэндлеры принимают ProfileManager как зависимость

@stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
async def show_profile(message: types.Message, profile_manager: ProfileManager):
    """Хэндлер команды /профиль или 'профиль'. Добавлен параметр bot."""
    profile = await profile_manager.get_user_profile(message.from_user)

    if not profile:
        await message.reply("❌ Не удалось загрузить профиль!")
        return

    # Передаем message.from_user (для данных пользователя)
    # Передаем profile (для данных профиля)
    # Передаем bot (для загрузки аватарки)
    image_bytes = await profile_manager.generate_profile_image(message.from_user, profile)

    input_file = BufferedInputFile(image_bytes.getvalue(), filename="profile.png")
    await message.answer_photo(
        photo=input_file,
        caption=f"Профиль пользователя {message.from_user.first_name}" # Опционально: добавить подпись
    )

@stat_router.message(F.text.lower() == "работать")
async def do_work(message: types.Message, profile_manager: ProfileManager):
    """Хэндлер команды 'работать'."""
    user_id = message.from_user.id
    current_time = time.time()

    last_work_time = await profile_manager.get_last_work_time(user_id)
    time_elapsed = current_time - last_work_time
    time_left = ProfileConfig.WORK_COOLDOWN_SECONDS - time_elapsed

    if time_elapsed < ProfileConfig.WORK_COOLDOWN_SECONDS:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        await message.reply(f"⏳ Работать можно будет через {minutes_left} мин {seconds_left} сек.")
    else:
        reward = random.randint(ProfileConfig.WORK_REWARD_MIN, ProfileConfig.WORK_REWARD_MAX)
        task = random.choice(ProfileConfig.WORK_TASKS)
        await profile_manager.update_lumcoins(user_id, reward)
        await profile_manager.update_last_work_time(user_id, current_time)
        # Используем user.first_name для более личного обращения
        await message.reply(f"{message.from_user.first_name} {task} и заработал(а) {reward} LUMcoins!")

@stat_router.message(F.text.lower() == "магазин")
async def show_shop(message: types.Message, profile_manager: ProfileManager):
    """Хэндлер команды 'магазин'."""
    # manager.get_available_backgrounds не асинхронный и не обращается к БД в этом коде,
    # но все равно используем переданный менеджер для доступа к конфигу
    shop_items = profile_manager.get_available_backgrounds()
    text = "🛍️ **Магазин фонов** 🛍️\n\n"
    text += "Напишите название фона из списка, чтобы купить его:\n\n"
    for key, item in shop_items.items():
        text += f"- `{key}`: {item['name']} ({item['cost']} LUMcoins)\n"
    await message.reply(text, parse_mode="Markdown")

# Хэндлер для покупки фона по ключу (например, "space", "nature" и т.д.)
# Этот хэндлер сработает, если текст сообщения ТОЧНО совпадает с одним из ключей магазина.
# Убедитесь, что эти ключи не пересекаются с другими командами или важными словами.
@stat_router.message(F.text.lower().in_(ProfileConfig.BACKGROUND_SHOP.keys()))
async def buy_background(message: types.Message, profile_manager: ProfileManager):
    """Хэндлер для покупки фона из магазина."""
    user_id = message.from_user.id
    command = message.text.lower()
    shop_items = profile_manager.get_available_backgrounds()

    # Проверка уже сделана в F.text.lower().in_(), но оставим для явности и получения item
    if command in shop_items:
        item = shop_items[command]
        user_coins = await profile_manager.get_lumcoins(user_id)
        if user_coins >= item['cost']:
            await profile_manager.update_lumcoins(user_id, -item['cost'])
            await profile_manager.set_background(user_id, item['url'])
            await message.reply(f"✅ Вы успешно приобрели фон '{item['name']}' за {item['cost']} LUMcoins!")
        else:
            await message.reply(f"❌ Недостаточно LUMcoins! Цена фона '{item['name']}': {item['cost']}, у вас: {user_coins}.")
    # Else ветка здесь не нужна, так как F.text.in_ уже фильтрует

@stat_router.message() # Хэндлер для всех остальных сообщений
async def track_message_activity(message: types.Message, profile_manager: ProfileManager):
    """Хэндлер для отслеживания активности сообщений (для опыта и уровня)."""
    # Игнорируем сообщения, которые являются ответами на самого себя или системные сообщения
    if message.from_user.id == message.bot.id or message.content_type != types.ContentType.TEXT:
         return

    # Дополнительная проверка, если это не приватный чат (обычно трекают в группах)
    # if message.chat.type == ChatType.PRIVATE:
    #      return

    user_id = message.from_user.id

    # Получаем профиль ПЕРЕД обновлением, чтобы сравнить уровень и монеты
    old_profile = await profile_manager.get_user_profile(message.from_user)
    if not old_profile:
         # Это может произойти, если get_user_profile по какой-то причине не смог создать/получить профиль.
         # Логгируем и пропускаем. get_user_profile уже логгирует ошибку.
         logger.error(f"Failed to get old profile for user_id {user_id} in track_message_activity.")
         return

    old_level = old_profile.get('level', 1)
    old_lumcoins = old_profile.get('lumcoins', 0) # Получаем старое количество монет

    # Обновляем сообщения, exp и level в базе данных
    # record_message теперь не возвращает уровень и награду
    await profile_manager.record_message(message.from_user)

    # Снова получаем профиль, чтобы проверить новый уровень и монеты
    new_profile = await profile_manager.get_user_profile(message.from_user)
    if not new_profile:
        # Снова, если не удалось получить новый профиль после обновления
        logger.error(f"Failed to get new profile for user_id {user_id} after record_message.")
        return

    new_level = new_profile.get('level', 1)
    new_lumcoins = new_profile.get('lumcoins', 0)
    # Считаем заработанные монеты как разницу между новым и старым значением
    lumcoins_earned_from_level = new_lumcoins - old_lumcoins

    # Если уровень повысился И были начислены монеты (награда за уровень), отправляем уведомление
    # Проверка lumcoins_earned_from_level > 0 гарантирует, что уведомление идет
    # именно о награде за уровень, а не просто о любом обновлении монет.
    if new_level > old_level and lumcoins_earned_from_level > 0:
        await message.reply(
            f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг(ла) Уровня {new_level}! "
            f"Награда: {lumcoins_earned_from_level} LUMcoins."
        )

# Этот хэндлер сработает последним, если предыдущие не сработали.
# В текущей конфигурации, track_message_activity обрабатывает ВСЕ текстовые сообщения.
# Если вам нужно логгировать сообщения, которые *не* обрабатываются track_message_activity
# (например, команды, стикеры и т.п.), то этот хэндлер должен быть ПЕРЕД track_message_activity
# и иметь более широкий фильтр или быть без фильтра, но track_message_activity
# должен быть ограничен только текстовыми сообщениями без команд и ключей магазина.
# В текущем коде track_message_activity уже обрабатывает все, поэтому этот хэндлер недостижим.
# Убираем его, чтобы избежать путаницы.
# @stat_router.message()
# async def debug_unhandled(message: types.Message):
#     print(f"🔴 Необработанное сообщение: '{message.text}' (User ID: {message.from_user.id})")


def setup_stat_handlers(dp: Dispatcher):
    """
    Функция для подключения роутера статистики к главному диспетчеру.
    Вызывается в главном скрипте запуска бота.
    """
    dp.include_router(stat_router)
    logger.info("Stat router included.")
    # Эта функция просто подключает роутер. Она не занимается созданием
    # и подключением ProfileManager к Dispatcher'у. Это должно происходить
    # в главном файле при запуске бота.
    return dp

# ВАЖНО: Этот файл является МОДУЛЕМ.
# Для запуска бота вам нужен ОТДЕЛЬНЫЙ ГЛАВНЫЙ СКРИПТ (например, main.py),
# который импортирует этот модуль, создает ProfileManager,
# устанавливает соединение с базой данных и запускает dp.start_polling,
# ПЕРЕДАВАЯ ТУДА СОЗДАННЫЙ ProfileManager ДЛЯ ИНЖЕКЦИИ.
# Пример такого главного скрипта был показан в предыдущем ответе.
# Не запускайте этот файл напрямую, если он не содержит функцию main()
# с логикой запуска бота, как было показано ранее.
