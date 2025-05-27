import aiosqlite

import asyncio

from pathlib import Path

from typing import List, Tuple, Optional, Dict, Any

from datetime import datetime

import logging

logger = logging.getLogger(__name__)

DB_FILE = Path("data") / "bot_database.db"

DB_FILE.parent.mkdir(exist_ok=True)

async def init_db():

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                last_active_ts REAL DEFAULT 0
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS value_subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscribed_ts REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS dialog_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                mode TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')), -- Добавим роль для явности
                content TEXT NOT NULL, -- Одно поле для контента
                -- user_message TEXT NOT NULL, -- Устарело, используем role и content
                -- bot_response TEXT NOT NULL, -- Устарело, используем role и content
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_dialog_history_user_ts ON dialog_history (user_id, timestamp DESC)
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_modes (
                user_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'saharoza', -- Добавим DEFAULT
                rating_opportunities_count INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS analytics_interactions (
                interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                mode TEXT NOT NULL, -- Режим во время взаимодействия
                action_type TEXT NOT NULL DEFAULT 'message', -- Тип действия (message, command, callback, etc.)
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_interactions_user_ts_mode ON analytics_interactions (user_id, timestamp DESC, mode)
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS analytics_ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rated_message_id INTEGER, -- Опционально: ID сообщения бота, которое оценили
                dialog_history_id INTEGER, -- Опционально: ссылка на запись в dialog_history (если оценка относится к конкретному ответу)
                timestamp REAL NOT NULL,
                rating INTEGER NOT NULL CHECK(rating IN (0, 1)), -- 0 для дизлайка, 1 для лайка
                message_preview TEXT, -- Превью сообщения, к которому относится оценка
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(dialog_history_id) REFERENCES dialog_history(history_id) ON DELETE SET NULL
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS rp_user_stats (
                user_id INTEGER PRIMARY KEY,
                hp INTEGER NOT NULL DEFAULT 100,
                heal_cooldown_ts REAL NOT NULL DEFAULT 0,
                recovery_end_ts REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        await db.commit()

    logger.info("Database initialized successfully.")

async def ensure_user(user_id: int, username: Optional[str], first_name: str):

    current_ts = datetime.now().timestamp()

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT INTO users (user_id, username, first_name, last_active_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active_ts = excluded.last_active_ts
        ''', (user_id, username, first_name, current_ts))

        await db.execute('''
            INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count)
            VALUES (?, 'saharoza', 0)
        ''', (user_id,))

        await db.execute('''
            INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)
        ''', (user_id,))

        await db.commit()

async def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute('SELECT user_id, username, first_name, last_active_ts FROM users WHERE user_id = ?', (user_id,)) as cursor:

            row = await cursor.fetchone()

            if row:

                return {

                    "user_id": row[0],

                    "username": row[1],

                    "first_name": row[2],

                    "last_active": datetime.fromtimestamp(row[3]).isoformat() if row[3] and row[3] > 0 else 'N/A'

                }

            return None

async def add_value_subscriber(user_id: int):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT OR IGNORE INTO value_subscriptions (user_id, subscribed_ts) VALUES (?, ?)
        ''', (user_id, datetime.now().timestamp()))

        await db.commit()

async def remove_value_subscriber(user_id: int):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('DELETE FROM value_subscriptions WHERE user_id = ?', (user_id,))

        await db.commit()

async def get_value_subscribers() -> List[int]:

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute('SELECT user_id FROM value_subscriptions') as cursor:

            rows = await cursor.fetchall()

            return [row[0] for row in rows]

async def is_value_subscriber(user_id: int) -> bool:

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute('SELECT 1 FROM value_subscriptions WHERE user_id = ?', (user_id,)) as cursor:

            return await cursor.fetchone() is not None

async def add_dialog_history(user_id: int, mode: str, user_message_text: str, bot_response_text: str):

    current_ts = datetime.now().timestamp()

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT INTO dialog_history (user_id, timestamp, mode, role, content)
            VALUES (?, ?, ?, 'user', ?)
        ''', (user_id, current_ts - 0.001, mode, user_message_text))

        await db.execute('''
            INSERT INTO dialog_history (user_id, timestamp, mode, role, content)
            VALUES (?, ?, ?, 'assistant', ?)
        ''', (user_id, current_ts, mode, bot_response_text))

        await db.execute('''
            DELETE FROM dialog_history
            WHERE history_id NOT IN (
                SELECT history_id FROM dialog_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20
            ) AND user_id = ?
        ''', (user_id, user_id))

        await db.commit()

async def get_dialog_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute('''
            SELECT role, content, mode, timestamp FROM dialog_history
            WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit)) as cursor:

            rows = await cursor.fetchall()

            history = [{"role": row[0], "content": row[1], "mode": row[2], "timestamp": row[3]} for row in reversed(rows)]

            return history

async def get_dialog_history_for_ollama(user_id: int, limit_turns: int = 5) -> List[Dict[str, str]]:

    raw_history = await get_dialog_history(user_id, limit=limit_turns * 2)

    ollama_history = []

    user_msg_temp = None

    for entry in raw_history:

        if entry["role"] == "user":

            user_msg_temp = entry["content"]

        elif entry["role"] == "assistant" and user_msg_temp is not None:

            ollama_history.append({"user": user_msg_temp, "assistant": entry["content"]})

            user_msg_temp = None

        elif entry["role"] == "assistant" and user_msg_temp is None:

            logger.warning(f"Orphan assistant message in history for user {user_id}, skipping for Ollama.")

    return ollama_history

async def set_user_mode(user_id: int, mode: str):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT INTO user_modes (user_id, mode) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET mode = excluded.mode
        ''', (user_id, mode))

        await db.commit()

async def get_user_mode_and_rating_opportunity(user_id: int) -> Dict[str, Any]:

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count)
            VALUES (?, 'saharoza', 0)
        ''', (user_id,))

        async with db.execute('SELECT mode, rating_opportunities_count FROM user_modes WHERE user_id = ?', (user_id,)) as cursor:

            row = await cursor.fetchone()

            return {"mode": row[0], "rating_opportunities_count": row[1]}

async def increment_rating_opportunity_count(user_id: int):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            UPDATE user_modes
            SET rating_opportunities_count = rating_opportunities_count + 1
            WHERE user_id = ?
        ''', (user_id,))

        await db.commit()

async def reset_rating_opportunity_count(user_id: int):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('UPDATE user_modes SET rating_opportunities_count = 0 WHERE user_id = ?', (user_id,))

        await db.commit()

async def log_interaction_db(user_id: int, mode: str, action_type: str = "message"):

    current_ts = datetime.now().timestamp()

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT INTO analytics_interactions (user_id, timestamp, mode, action_type) VALUES (?, ?, ?, ?)
        ''', (user_id, current_ts, mode, action_type))

        await db.execute('UPDATE users SET last_active_ts = ? WHERE user_id = ?', (current_ts, user_id))

        await db.commit()

async def log_rating_db(user_id: int, rating: int, message_preview: str, rated_msg_id: Optional[int] = None, dialog_hist_id: Optional[int] = None):

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('''
            INSERT INTO analytics_ratings (user_id, timestamp, rating, message_preview, rated_message_id, dialog_history_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, datetime.now().timestamp(), rating, message_preview[:500], rated_msg_id, dialog_hist_id))

        await db.commit()

async def get_user_stats_db(user_id: int) -> Dict[str, Any]:

    stats = {"count": 0, "last_mode": "N/A", "last_active": "N/A"}

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute('SELECT COUNT(*) FROM analytics_interactions WHERE user_id = ?', (user_id,)) as cursor:

            count_row = await cursor.fetchone()

            if count_row: stats["count"] = count_row[0]

        user_info = await get_user_info(user_id)

        if user_info:

            stats["last_active"] = user_info["last_active"]

        async with db.execute('SELECT mode FROM analytics_interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,)) as cursor:

            last_interaction_mode = await cursor.fetchone()

            if last_interaction_mode:

                stats["last_mode"] = last_interaction_mode[0]

            else:

                async with db.execute('SELECT mode FROM user_modes WHERE user_id = ?', (user_id,)) as mode_cursor:

                    current_mode = await mode_cursor.fetchone()

                    if current_mode: stats["last_mode"] = current_mode[0]

    return stats

async def get_rp_stats(user_id: int) -> Dict[str, Any]:

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)', (user_id,))

        async with db.execute('SELECT hp, heal_cooldown_ts, recovery_end_ts FROM rp_user_stats WHERE user_id = ?', (user_id,)) as cursor:

            row = await cursor.fetchone()

            if row:

                return {"hp": row[0], "heal_cooldown_ts": row[1], "recovery_end_ts": row[2]}

            else:

                logger.error(f"CRITICAL: RP stats row not found for user_id {user_id} after INSERT OR IGNORE. Schema defaults might be missing or DB error.")

                return {"hp": 100, "heal_cooldown_ts": 0, "recovery_end_ts": 0}

async def update_rp_stats(user_id: int, hp: Optional[int] = None, heal_cooldown_ts: Optional[float] = None, recovery_end_ts: Optional[float] = None):

    updates = []

    params: List[Any] = []

    if hp is not None:

        updates.append("hp = ?")

        params.append(hp)

    if heal_cooldown_ts is not None:

        updates.append("heal_cooldown_ts = ?")

        params.append(heal_cooldown_ts)

    if recovery_end_ts is not None:

        updates.append("recovery_end_ts = ?")

        params.append(recovery_end_ts)

    if not updates: return

    query = f"UPDATE rp_user_stats SET {', '.join(updates)} WHERE user_id = ?"

    params.append(user_id)

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute('INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)', (user_id,))

        await db.execute(query, tuple(params))

        await db.commit()

def read_value_from_file(file_path: Path) -> Optional[str]:

    try:

        with open(file_path, 'r', encoding='utf-8') as file:

            for line in file:

                stripped_line = line.strip()

                if stripped_line.startswith("check = "):

                    value = stripped_line[len("check = "):].strip()

                    return value

    except FileNotFoundError:

        logger.warning(f"File for value monitoring not found: {file_path}")

    except Exception as e:

        logger.error(f"Error reading value file ({file_path}): {e}", exc_info=True)

    return None

async def get_users_for_hp_recovery(current_timestamp: float, min_hp_level_inclusive: int) -> List[Tuple[int, int]]:

    query = """
        SELECT user_id, hp
        FROM rp_user_stats
        WHERE hp <= ? AND recovery_end_ts > 0 AND recovery_end_ts <= ?
    """

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute(query, (min_hp_level_inclusive, current_timestamp)) as cursor:

            rows = await cursor.fetchall()

            return [(row[0], row[1]) for row in rows]