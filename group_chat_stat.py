from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os
import time
from datetime import datetime, timedelta
import json
from collections import defaultdict

# Создаем отдельный роутер для статистики
stat_router = Router(name="stat_router")
stat_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# Конфигурация
USER_DATA_FILE = "data/user_activity.json"
HP_FILE = "hp.txt"
os.makedirs("data", exist_ok=True)

# Стили оформления
STATS_STYLE = {
    "header": "✨ <b>{username}</b> ✨",
    "divider": "▬▬▬▬▬▬▬▬▬▬▬▬▬",
    "stat_row": "┃ {stat:<15} ┃ {value:>5} ┃",
    "footer": "➖➖➖➖➖➖➖➖➖"
}

class UserActivityTracker:
    def __init__(self):
        self.data = self._load_data()
        self._schedule_daily_reset()
    
    def _load_data(self):
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                # Добавляем поле hp если его нет
                for user_id, user_data in data.items():
                    if "hp" not in user_data:
                        user_data["hp"] = 0
                return defaultdict(self._default_user_data, data)
        return defaultdict(self._default_user_data)
    
    def _default_user_data(self):
        return {
            "daily_messages": 0,
            "total_messages": 0,
            "last_active": 0,
            "hp": 0  # Гарантируем наличие поля
        }
    
    def _schedule_daily_reset(self):
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        self.next_reset = midnight.timestamp()
    
    def _check_reset(self):
        if time.time() > self.next_reset:
            for user in self.data.values():
                user["daily_messages"] = 0
            self._schedule_daily_reset()
            self._save_data()
    
    def _save_data(self):
        with open(USER_DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def _load_hp_data(self):
        hp_data = {}
        if os.path.exists(HP_FILE):
            with open(HP_FILE, "r", encoding='utf-8') as f:
                for line in f:
                    if ":" in line:
                        parts = line.strip().split(":")
                        if len(parts) >= 2:
                            username = parts[0].strip()
                            try:
                                hp = int(parts[1].strip())
                                hp_data[username] = hp
                            except ValueError:
                                continue
        return hp_data
    
    def record_activity(self, user_id: int, username: str):
        self._check_reset()
        user_id = str(user_id)
        
        if user_id not in self.data:
            self.data[user_id] = self._default_user_data()
            
        user_data = self.data[user_id]
        user_data["daily_messages"] += 1
        user_data["total_messages"] += 1
        user_data["last_active"] = time.time()
        
        hp_data = self._load_hp_data()
        user_key = f"@{username}" if not username.startswith("@") else username
        user_data["hp"] = hp_data.get(user_key, 0)
        
        self._save_data()
    
    def get_user_stats(self, user_id: int, username: str):
        user_id = str(user_id)
        if user_id not in self.data:
            return None
        
        hp_data = self._load_hp_data()
        user_key = f"@{username}" if not username.startswith("@") else username
        self.data[user_id]["hp"] = hp_data.get(user_key, 0)
        
        return self.data[user_id]
    
    def get_top_users(self, count=10):
        users = []
        hp_data = self._load_hp_data()
        
        for user_id, data in self.data.items():
            # Ищем username по HP (может быть несколько пользователей с одинаковым HP)
            possible_usernames = [k for k, v in hp_data.items() if v == data.get("hp", 0)]
            username = possible_usernames[0] if possible_usernames else f"User_{user_id}"
            
            users.append({
                "username": username,
                "messages": data.get("total_messages", 0),
                "hp": data.get("hp", 0)
            })
        
        # Сортируем по количеству сообщений (по убыванию)
        users.sort(key=lambda x: x["messages"], reverse=True)
        return users[:count]

tracker = UserActivityTracker()

def format_stats_message(username: str, stats: dict):
    message = [
        STATS_STYLE["header"].format(username=username),
        STATS_STYLE["divider"],
        STATS_STYLE["stat_row"].format(stat="Сообщений сегодня", value=stats.get("daily_messages", 0)),
        STATS_STYLE["stat_row"].format(stat="Всего сообщений", value=stats.get("total_messages", 0)),
        STATS_STYLE["stat_row"].format(stat="HP", value=stats.get("hp", 0)),
        STATS_STYLE["footer"]
    ]
    return "\n".join(message)

def format_top_message(top_users: list):
    if not top_users:
        return "❌ Нет данных для отображения топа"
    
    message = ["🏆 <b>ТОП АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ</b> 🏆", STATS_STYLE["divider"]]
    
    for i, user in enumerate(top_users, 1):
        message.append(
            f"{i}. {user['username']}: "
            f"✉️ {user.get('messages', 0)} | "
            f"❤️ {user.get('hp', 0)}"
        )
    
    message.append(STATS_STYLE["footer"])
    return "\n".join(message)

@stat_router.message(F.text.lower() == "статистика")
async def show_stats(message: types.Message):
    user = message.from_user
    stats = tracker.get_user_stats(user.id, user.username or user.first_name)
    
    if not stats:
        await message.reply("❌ Статистика не найдена!")
        return
    
    formatted_stats = format_stats_message(
        user.username or user.first_name,
        stats
    )
    
    await message.reply(formatted_stats, parse_mode="HTML")

@stat_router.message(F.text.lower() == "топ стат")
async def show_top_stats(message: types.Message):
    top_users = tracker.get_top_users()
    formatted_top = format_top_message(top_users)
    await message.reply(formatted_top, parse_mode="HTML")

@stat_router.message()
async def track_message_activity(message: types.Message):
    user = message.from_user
    tracker.record_activity(user.id, user.username or user.first_name)

def setup_stat_handlers(dp):
    dp.include_router(stat_router)
    return dp