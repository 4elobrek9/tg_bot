import aiosqlite
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

DB_FILE = Path("data") / "bot_database.db"
DB_FILE.parent.mkdir(exist_ok=True)

# --- Инициализация БД ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # Пользователи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                last_active_ts REAL DEFAULT 0 
            )
        ''')
        
        # Подписки на мониторинг (/val)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS value_subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscribed_ts REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE 
            )
        ''')

        # История диалогов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS dialog_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                mode TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_dialog_history_user_ts ON dialog_history (user_id, timestamp DESC)
        ''')

        # Режим общения пользователя и счетчик возможностей оценки
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_modes (
                user_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL,
                rating_opportunities_count INTEGER DEFAULT 0, -- НОВЫЙ СТОЛБЕЦ
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        
        # Аналитика: взаимодействия
        await db.execute('''
            CREATE TABLE IF NOT EXISTS analytics_interactions (
                interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                mode TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_interactions_user_ts ON analytics_interactions (user_id, timestamp DESC)
        ''')

        # Аналитика: оценки
        await db.execute('''
            CREATE TABLE IF NOT EXISTS analytics_ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                rating INTEGER NOT NULL, 
                message_preview TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # RP Статистика Пользователей
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
    print("Database initialized successfully.")

# --- Пользователи ---
async def ensure_user(user_id: int, username: Optional[str], first_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO users (user_id, username, first_name, last_active_ts) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active_ts = excluded.last_active_ts
        ''', (user_id, username, first_name, datetime.now().timestamp()))
        # Также убедимся, что запись в user_modes существует
        await db.execute('''
            INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count) 
            VALUES (?, 'saharoza', 0)
        ''', (user_id,))
        await db.commit()

async def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
     async with aiosqlite.connect(DB_FILE) as db:
         async with db.execute('SELECT user_id, username, first_name, last_active_ts FROM users WHERE user_id = ?', (user_id,)) as cursor:
             row = await cursor.fetchone()
             if row:
                 return {"user_id": row[0], "username": row[1], "first_name": row[2], "last_active": datetime.fromtimestamp(row[3]).isoformat() if row[3] else 'N/A'}
             return None

# --- Подписки на /val ---
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

# --- История диалогов ---
async def add_dialog_history(user_id: int, mode: str, user_msg: str, bot_msg: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO dialog_history (user_id, timestamp, mode, user_message, bot_response)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, datetime.now().timestamp(), mode, user_msg, bot_msg))
        await db.execute('''
            DELETE FROM dialog_history 
            WHERE history_id NOT IN (
                SELECT history_id FROM dialog_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20 
            ) AND user_id = ? 
        ''', (user_id, user_id))
        await db.commit()

async def get_dialog_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]: # Увеличил лимит для пересылки
    """Получает последние N записей из истории диалога пользователя. Добавляет роль."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('''
            SELECT user_message, bot_response, mode, timestamp FROM dialog_history
            WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            # Возвращаем в правильном порядке (старые -> новые)
            history = []
            for row in reversed(rows):
                history.append({"role": "user", "content": row[0], "mode": row[2], "timestamp": row[3]})
                history.append({"role": "assistant", "content": row[1], "mode": row[2], "timestamp": row[3]})
            return history
            
async def get_dialog_history_for_ollama(user_id: int, limit: int = 5) -> List[Dict[str, str]]:
    """Получает историю для Ollama (только user/bot сообщения)."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('''
            SELECT user_message, bot_response FROM dialog_history
            WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [{"user": row[0], "bot": row[1]} for row in reversed(rows)]


# --- Режим общения и счетчик оценок ---
async def set_user_mode(user_id: int, mode: str):
    async with aiosqlite.connect(DB_FILE) as db:
        # При смене режима не сбрасываем счетчик оценок, т.к. он общий для пользователя, а не для режима
        await db.execute('''
            INSERT INTO user_modes (user_id, mode) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET mode = excluded.mode
        ''', (user_id, mode))
        await db.commit()

async def get_user_mode_and_rating_opportunity(user_id: int) -> Dict[str, Any]:
    """Получает текущий режим и количество предоставленных возможностей оценки."""
    async with aiosqlite.connect(DB_FILE) as db:
        # Убедимся, что запись существует (на случай, если ensure_user не был вызван ранее для этого user_id)
        await db.execute('''
            INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count) 
            VALUES (?, 'saharoza', 0)
        ''', (user_id,))
        async with db.execute('SELECT mode, rating_opportunities_count FROM user_modes WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"mode": row[0], "rating_opportunities_count": row[1]}
            return {"mode": "saharoza", "rating_opportunities_count": 0} # Дефолт

async def increment_rating_opportunity_count(user_id: int):
    """Увеличивает счетчик предоставленных возможностей оценки для пользователя."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE user_modes 
            SET rating_opportunities_count = rating_opportunities_count + 1 
            WHERE user_id = ?
        ''', (user_id,))
        await db.commit()

async def reset_rating_opportunity_count(user_id: int):
    """Сбрасывает счетчик предоставленных возможностей оценки (например, при /reset)."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE user_modes SET rating_opportunities_count = 0 WHERE user_id = ?', (user_id,))
        await db.commit()
    
# --- Аналитика ---
async def log_interaction_db(user_id: int, mode: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO analytics_interactions (user_id, timestamp, mode) VALUES (?, ?, ?)
        ''', (user_id, datetime.now().timestamp(), mode))
        await db.execute('UPDATE users SET last_active_ts = ? WHERE user_id = ?', (datetime.now().timestamp(), user_id))
        await db.commit()

async def log_rating_db(user_id: int, rating: int, message: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO analytics_ratings (user_id, timestamp, rating, message_preview) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, datetime.now().timestamp(), rating, message[:500]))
        await db.commit()

async def get_user_stats_db(user_id: int) -> Dict[str, Any]:
    stats = {"count": 0, "last_mode": "еще не выбран", "last_active": "еще не активен"}
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT COUNT(*) FROM analytics_interactions WHERE user_id = ?', (user_id,)) as cursor:
            count_row = await cursor.fetchone()
            stats["count"] = count_row[0] if count_row else 0
            
        async with db.execute('SELECT mode, timestamp FROM analytics_interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,)) as cursor:
            last_interaction = await cursor.fetchone()
            if last_interaction:
                stats["last_mode"] = last_interaction[0]
                stats["last_active"] = datetime.fromtimestamp(last_interaction[1]).isoformat()
    return stats
    
# --- RP Статистика ---
async def get_rp_stats(user_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)', (user_id,))
        async with db.execute('SELECT hp, heal_cooldown_ts, recovery_end_ts FROM rp_user_stats WHERE user_id = ?', (user_id,)) as cursor:
             row = await cursor.fetchone()
             if row:
                 return {"hp": row[0], "heal_cooldown_ts": row[1], "recovery_end_ts": row[2]}
             else: 
                 return {"hp": 100, "heal_cooldown_ts": 0, "recovery_end_ts": 0} 

async def update_rp_stats(user_id: int, hp: Optional[int] = None, heal_cooldown_ts: Optional[float] = None, recovery_end_ts: Optional[float] = None):
    updates = []
    params = []
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

# --- Мониторинг файла ---
async def read_value_from_file(file_path: Path) -> Optional[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                stripped_line = line.strip()
                if stripped_line.startswith("check = "):
                    value = stripped_line[len("check = "):].strip()
                    return value
    except FileNotFoundError:
        print(f"File not found: {file_path}") # Заменить на logger.warning
    except Exception as e:
        print(f"File read error ({file_path}): {e}") # Заменить на logger.error
    return None
