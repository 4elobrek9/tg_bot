from aiogram import Router, types, F
from aiogram.enums import ChatType
import os
import time
from datetime import datetime, timedelta
import json
from collections import defaultdict
from typing import Dict, Any
from group_chat import *

# Инициализация роутера
stat_router = Router(name="stat_router")
stat_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# Стили оформления
STATS_STYLE = {
    "divider": "-------------------",
    "footer": " "
}

# Конфигурация
class StatConfig:
    USER_DATA_FILE = "data/user_activity.json"
    HP_FILE = "data/hp_data.txt"
    DAILY_TOP_REWARD = 1

class UserActivityTracker:
    def __init__(self):
        self.data = self._load_data()
        self._schedule_daily_reset()
        self.daily_top_users = {}

    def _load_data(self) -> Dict[str, Any]:
        try:
            if os.path.exists(StatConfig.USER_DATA_FILE):
                with open(StatConfig.USER_DATA_FILE, "r", encoding='utf-8') as f:
                    data = json.load(f)
                    converted_data = {}
                    for user_id, user_data in data.items():
                        if isinstance(user_id, str) and user_id.isdigit():
                            username = user_data.get("username", f"user_{user_id}")
                            converted_data[username] = user_data
                        else:
                            converted_data[user_id] = user_data

                    for user_data in converted_data.values():
                        user_data.setdefault("hp", 0)
                        user_data.setdefault("daily_flames", 0)
                        user_data.setdefault("total_flames", 0)
                        user_data.setdefault("daily_top_count", 0)

                    return defaultdict(self._default_user_data, converted_data)
            return defaultdict(self._default_user_data)
        except (json.JSONDecodeError, IOError):
            return defaultdict(self._default_user_data)

    def _default_user_data(self) -> Dict[str, Any]:
        return {
            "daily_messages": 0,
            "total_messages": 0,
            "last_active": 0,
            "hp": 0,
            "daily_flames": 0,
            "total_flames": 0,
            "daily_top_count": 0,
            "reward_level": "low",
            "current_bg": "default_bg.jpg",
            "unlocked_bgs": ["default_bg.jpg"]
        }

    def _schedule_daily_reset(self) -> None:
        now = datetime.now()
        midnight = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now > midnight:
            midnight += timedelta(days=1)
        self.next_reset = midnight.timestamp()

    def _check_reset(self) -> None:
        if time.time() > self.next_reset:
            if self.daily_top_users:
                top_user = max(self.daily_top_users.items(), key=lambda x: x[1])
                if top_user[0] in self.data:
                    self.data[top_user[0]]["daily_flames"] += StatConfig.DAILY_TOP_REWARD
                    self.data[top_user[0]]["total_flames"] += StatConfig.DAILY_TOP_REWARD
                    self.data[top_user[0]]["daily_top_count"] += 1

            for user_data in self.data.values():
                user_data["daily_messages"] = 0
                user_data["daily_flames"] = 0

            self.daily_top_users = {}
            self._schedule_daily_reset()
            self._save_data()

    def _save_data(self) -> None:
        os.makedirs(os.path.dirname(StatConfig.USER_DATA_FILE), exist_ok=True)
        with open(StatConfig.USER_DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(dict(self.data), f, ensure_ascii=False, indent=2)

    def _load_hp_data(self) -> Dict[str, int]:
        hp_data = {}
        if os.path.exists(StatConfig.HP_FILE):
            with open(StatConfig.HP_FILE, "r", encoding='utf-8') as f:
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

    def record_activity(self, user: types.User) -> None:
        self._check_reset()
        username = f"@{user.username}" if user.username else f"@{user.first_name}"

        if username not in self.data:
            self.data[username] = self._default_user_data()
            self.data[username]["username"] = username

        user_data = self.data[username]
        user_data["daily_messages"] += 1
        user_data["total_messages"] += 1
        user_data["last_active"] = time.time()

        if username not in self.daily_top_users:
            self.daily_top_users[username] = 0
        self.daily_top_users[username] += 1

        hp_data = self._load_hp_data()
        user_data["hp"] = hp_data.get(username, 0)

        self._save_data()

    def get_user_stats(self, user: types.User) -> Dict[str, Any]:
        username = f"@{user.username}" if user.username else f"@{user.first_name}"
        if username not in self.data:
            return None

        hp_data = self._load_hp_data()
        self.data[username]["hp"] = hp_data.get(username, 0)
        return self.data[username]

    def get_top_users(self, count: int = 10) -> list:
        self._check_reset()
        return sorted(
            [
                {
                    "username": username,
                    "messages": data.get("daily_messages", 0),
                    "hp": data.get("hp", 0),
                    "flames": data.get("total_flames", 0)
                }
                for username, data in self.data.items()
                if isinstance(data, dict)
            ],
            key=lambda x: x["messages"],
            reverse=True
        )[:count]

def format_top_message(top_users: list) -> str:
    if not top_users:
        return "❌ Нет данных для отображения топа"

    message = ["🏆 <b>ТОП УЧАСТНИКОВ</b> 🏆", STATS_STYLE["divider"]]
    for i, user in enumerate(top_users, 1):
        username = user.get("username", "Неизвестный")
        flames = "🔥" * user.get("flames", 0)
        message.append(
            f"{i}. {username}: ✉️ {user.get('messages', 0)} | "
            f"❤️ {user.get('hp', 0)} | {flames}"
        )
    message.append(STATS_STYLE["footer"])
    return "\n".join(message)

def format_user_stats(username: str, stats: Dict[str, Any]) -> str:
    flames = "🔥" * stats.get("total_flames", 0)
    return (
        f"📊 <b>ПРОФИЛЬ {username}</b>\n{STATS_STYLE['divider']}\n"
        f"✉️ Сообщений сегодня: {stats.get('daily_messages', 0)}\n"
        f"✉️ Сообщений всего: {stats.get('total_messages', 0)}\n"
        f"❤️ HP: {stats.get('hp', 0)}\n"
        f"🔥 Всего flames: {stats.get('total_flames', 0)} {flames}\n"
        f"🏆 Топов дня: {stats.get('daily_top_count', 0)}\n"
        f"{STATS_STYLE['footer']}"
    )

@stat_router.message(F.text.lower() == "профиль")
async def show_profile(message: types.Message):
    tracker = UserActivityTracker()
    stats = tracker.get_user_stats(message.from_user)
    if not stats:
        await message.reply("❌ Статистика не найдена!")
        return
    
    username = f"@{message.from_user.username}" if message.from_user.username else f"@{message.from_user.first_name}"
    await message.reply(format_user_stats(username, stats), parse_mode="HTML")

@stat_router.message(F.text.lower() == "топ")
async def show_top_stats(message: types.Message):
    tracker = UserActivityTracker()
    top_users = tracker.get_top_users(10)
    await message.reply(format_top_message(top_users), parse_mode="HTML")

@stat_router.message()
async def track_message_activity(message: types.Message):
    tracker = UserActivityTracker()
    tracker.record_activity(message.from_user)

def setup_stat_handlers(dp):
    """Функция для безопасного подключения роутера"""
    if not any(r.name == "stat_router" for r in dp.sub_routers):
        dp.include_router(stat_router)
    return dp
