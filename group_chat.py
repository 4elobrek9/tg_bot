from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os
import time
from datetime import datetime, timedelta
import json
from collections import defaultdict
import logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# ====================== RP MODULE ======================

# Создаем отдельный роутер для RP
rp_router = Router(name="rp_router")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# ====================== КОНФИГУРАЦИЯ ======================
class Config:
    HP_FILE = "hp.txt"
    COOLDOWN_FILE = "cooldown.txt"
    USER_DATA_FILE = "data/user_activity.json"
    DEFAULT_HP = 100
    MAX_HP = 150
    MIN_HP = 0
    HEAL_COOLDOWN = 30  # 0.5 минут в секундах
    HP_RECOVERY_TIME = 600  # 10 минут в секундах
    HP_RECOVERY_AMOUNT = 10
    DAILY_TOP_REWARD = 1  # +1 огонёк за топ1 за день

# ====================== ДАННЫЕ ДЕЙСТВИЙ ======================
class Actions:
    RP_ACTIONS = [
        "ударить", "поцеловать", "обнять", "укусить",
        "погладить", "толкнуть", "ущипнуть", "шлепнуть", "пощечина",
        "пнуть", "схватить", "заплакать", "засмеяться",
        "удивиться", "разозлиться", "испугаться", "подмигнуть", "шепнуть",
        "издеваться"
    ]

    INTIMATE_ACTIONS = {
        "добрые": {
            "поцеловать": {"hp_change_target": +10, "hp_change_sender": -5},
            "обнять": {"hp_change_target": +15, "hp_change_sender": +15},
            "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
            "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"hp_change_target": +9, "hp_change_sender": -4},
            "напоить": {"hp_change_target": +6, "hp_change_sender": -3},
            "сделать массаж": {"hp_change_target": +15, "hp_change_sender": -4},
            "спеть песню": {"hp_change_target": +5, "hp_change_sender": -1},
            "подарить цветы": {"hp_change_target": +12, "hp_change_sender": -6},
            "подрочить": {"hp_change_target": +12, "hp_change_sender": +6},
        },
        "нейтральные": {
            "толкнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "схватить": {"hp_change_target": 0, "hp_change_sender": 0},
            "помахать": {"hp_change_target": 0, "hp_change_sender": 0},
            "кивнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "похлопать": {"hp_change_target": 0, "hp_change_sender": 0},
            "постучать": {"hp_change_target": 0, "hp_change_sender": 0},
            "попрощаться": {"hp_change_target": 0, "hp_change_sender": 0},
            "шепнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "почесать спинку": {"hp_change_target": +5, "hp_change_sender": 0},
        },
        "злые": {
            "уебать": {"hp_change_target": -20, "hp_change_sender": 0},
            "схватить за шею": {"hp_change_target": -25, "hp_change_sender": 0},
            "ударить": {"hp_change_target": -10, "hp_change_sender": 0},
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": 0},
            "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": 0},
            "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"hp_change_target": -80, "hp_change_sender": 0},
        }
    }

    # Полный список всех действий
    ALL_ACTIONS = {
        "Добрые действия": list(INTIMATE_ACTIONS["добрые"].keys()),
        "Нейтральные действия": list(INTIMATE_ACTIONS["нейтральные"].keys()),
        "Злые действия": list(INTIMATE_ACTIONS["злые"].keys())
    }

    # Список всех команд для проверки
    ALL_COMMANDS = (
        set(INTIMATE_ACTIONS["добрые"].keys()) | 
        set(INTIMATE_ACTIONS["нейтральные"].keys()) | 
        set(INTIMATE_ACTIONS["злые"].keys())
    )

# ====================== МОДЕЛЬ ДАННЫХ ======================
class UserHPManager:
    _instance = None
    user_hp = {}
    cooldowns = {}
    recovery_times = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_hp()
            cls._instance.load_cooldowns()
        return cls._instance

    def load_hp(self):
        """Загружает HP пользователей из файла"""
        if os.path.exists(Config.HP_FILE):
            with open(Config.HP_FILE, "r", encoding="utf-8") as file:
                for line in file:
                    if ": " in line:
                        username, hp = line.strip().split(": ", 1)
                        try:
                            self.user_hp[username] = int(hp)
                        except ValueError:
                            self.user_hp[username] = Config.DEFAULT_HP

    def load_cooldowns(self):
        """Загружает кулдауны из файла"""
        if os.path.exists(Config.COOLDOWN_FILE):
            with open(Config.COOLDOWN_FILE, "r", encoding="utf-8") as file:
                for line in file:
                    if ": " in line:
                        username, cooldown_time = line.strip().split(": ", 1)
                        self.cooldowns[username] = float(cooldown_time)

    def save_hp(self):
        """Сохраняет текущие HP пользователей в файл"""
        with open(Config.HP_FILE, "w", encoding="utf-8") as file:
            for username, hp in self.user_hp.items():
                file.write(f"{username}: {hp}\n")

    def save_cooldowns(self):
        """Сохраняет текущие кулдауны в файл"""
        with open(Config.COOLDOWN_FILE, "w", encoding="utf-8") as file:
            for username, cooldown_time in self.cooldowns.items():
                file.write(f"{username}: {cooldown_time}\n")

    def get_user_hp(self, username):
        """Возвращает HP пользователя"""
        if username not in self.user_hp:
            self.user_hp[username] = Config.DEFAULT_HP
        return self.user_hp[username]

    def update_user_hp(self, username, hp_change):
        """Обновляет HP пользователя с проверкой границ"""
        current_hp = self.get_user_hp(username)
        new_hp = max(Config.MIN_HP, min(Config.MAX_HP, current_hp + hp_change))
        self.user_hp[username] = new_hp
        self.save_hp()
        
        if new_hp <= 0 and username not in self.recovery_times:
            self.recovery_times[username] = time.time() + Config.HP_RECOVERY_TIME

    def check_cooldown(self, username):
        """Проверяет кулдаун пользователя"""
        current_time = time.time()
        if username in self.cooldowns and current_time < self.cooldowns[username]:
            return self.cooldowns[username] - current_time
        return 0

    def set_cooldown(self, username):
        """Устанавливает кулдаун для пользователя"""
        self.cooldowns[username] = time.time() + Config.HEAL_COOLDOWN
        self.save_cooldowns()

    def check_hp_recovery(self, username):
        """Проверяет и восстанавливает HP"""
        if username in self.recovery_times:
            if time.time() >= self.recovery_times[username]:
                self.update_user_hp(username, Config.HP_RECOVERY_AMOUNT)
                del self.recovery_times[username]
                return True
        return False

    def get_recovery_time(self, username):
        """Возвращает оставшееся время восстановления"""
        if username in self.recovery_times:
            remaining = self.recovery_times[username] - time.time()
            return max(0, remaining)
        return 0


# ====================== ОБРАБОТЧИК СООБЩЕНИЙ ======================
# progres..
# ====================== ХЭНДЛЕРЫ ======================
async def check_zero_hp(message: types.Message):
    """Проверяет нулевое HP пользователя"""
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    current_hp = hp_manager.get_user_hp(username)
    
    if current_hp <= 0:
        recovery_time = hp_manager.get_recovery_time(username)
        if recovery_time > 0:
            minutes = int(recovery_time // 60)
            seconds = int(recovery_time % 60)
            try:
                await message.bot.send_message(
                    message.from_user.id,
                    f"Ваше HP равно 0. Вы не можете совершать действия. "
                    f"Автоматическое восстановление {Config.HP_RECOVERY_AMOUNT} HP через {minutes} мин {seconds} сек."
                )
            except:
                pass
        await message.delete()
        return True
    return False

def get_command_from_text(text: str) -> tuple:
    """Извлекает команду и дополнительный текст из сообщения"""
    if text is None:  # Проверка на None
        return None, None
    text_lower = text.lower()
    for cmd in Actions.ALL_COMMANDS:
        if text_lower.startswith(cmd):
            command = cmd
            additional_text = text[len(cmd):].strip()
            return command, additional_text
    return None, None

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.lower().contains('заплакать')
)
async def handle_cry(message: types.Message):
    """Обработчик плача"""
    if await check_zero_hp(message):
        return
        
    sender = message.from_user
    sender_username = f"@{sender.username}" if sender.username else sender.first_name
    await message.reply(
        f"{sender_username} заплакал. Сейчас будет либо резня, "
        f"либо этот человек просто поплачет и успокоится. "
        f"Надеемся, что кто-нибудь похилит {sender_username}\n"
        f"(Довели вы клоуны🤡 бедного {sender_username})"
    )

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    lambda message: get_command_from_text(message.text)[0] is not None
)
async def handle_intimate_action(message: types.Message):
    """Обработчик RP-действий"""
    if await check_zero_hp(message):
        return
        
    if not message.reply_to_message:
        await message.reply("Пожалуйста, ответьте на сообщение, чтобы использовать эту команду.")
        return

    command, additional_word = get_command_from_text(message.text)
    if not command:
        return

    target_user = message.reply_to_message.from_user
    sender = message.from_user
    
    if target_user.id == sender.id:
        await message.reply("Вы не можете использовать команды на себе!")
        await message.delete()
        return

    target_username = f"@{target_user.username}" if target_user.username else target_user.first_name
    sender_username = f"@{sender.username}" if sender.username else sender.first_name

    if command in Actions.INTIMATE_ACTIONS["добрые"]:
        cooldown_remaining = hp_manager.check_cooldown(sender_username)
        if cooldown_remaining > 0:
            minutes = int(cooldown_remaining // 60)
            seconds = int(cooldown_remaining % 60)
            await message.reply(
                f"{sender_username}, лечащие команды можно использовать "
                f"раз в {Config.HEAL_COOLDOWN//60} минут. "
                f"Подождите еще {minutes} мин {seconds} сек."
            )
            await message.delete()
            return

    command_past = command[:-2] + "л" if command.endswith("ть") else command

    if command in Actions.INTIMATE_ACTIONS["добрые"]:
        action_data = Actions.INTIMATE_ACTIONS["добрые"][command]
        hp_manager.update_user_hp(target_username, action_data["hp_change_target"])
        hp_manager.update_user_hp(sender_username, action_data["hp_change_sender"])
        hp_manager.set_cooldown(sender_username)
        
        response = (
            f"{sender_username} {command_past} {target_username} {additional_word}. "
            f"{target_username} получает +{action_data['hp_change_target']} HP, "
        )
    elif command in Actions.INTIMATE_ACTIONS["нейтральные"]:
        response = f"{sender_username} {command_past} {target_username} {additional_word}."
    elif command in Actions.INTIMATE_ACTIONS["злые"]:
        action_data = Actions.INTIMATE_ACTIONS["злые"][command]
        hp_manager.update_user_hp(target_username, action_data["hp_change_target"])
        
        target_hp = hp_manager.get_user_hp(target_username)
        if target_hp <= 0:
            hp_manager.recovery_times[target_username] = time.time() + Config.HP_RECOVERY_TIME
            response = (
                f"{sender_username} {command_past} {target_username} {additional_word}. "
                f"{target_username} теряет сознание! "
                f"Автоматическое восстановление {Config.HP_RECOVERY_AMOUNT} HP через 10 минут."
            )
        else:
            response = (
                f"{sender_username} {command_past} {target_username} {additional_word}. "
                f"У {target_username} осталось {target_hp} HP."
            )

    await message.reply(response)
    await message.delete()

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.lower().startswith(("моё хп", "мое хп", "мой хп"))
)
async def handle_check_hp(message: types.Message):
    """Показывает текущее HP"""
    if await check_zero_hp(message):
        return
        
    sender = message.from_user
    sender_username = f"@{sender.username}" if sender.username else sender.first_name
    current_hp = hp_manager.get_user_hp(sender_username)
    
    if hp_manager.check_hp_recovery(sender_username):
        current_hp = hp_manager.get_user_hp(sender_username)
        await message.reply(f"{sender_username}, ваше HP восстановлено на {Config.HP_RECOVERY_AMOUNT}. Текущее HP: {current_hp}.")
    else:
        recovery_time = hp_manager.get_recovery_time(sender_username)
        if recovery_time > 0:
            minutes = int(recovery_time // 60)
            seconds = int(recovery_time % 60)
            await message.reply(
                f"{sender_username}, ваше HP: {current_hp}. "
                f"Восстановление {Config.HP_RECOVERY_AMOUNT} HP через {minutes} мин {seconds} сек."
            )
        else:
            await message.reply(f"{sender_username}, ваше HP: {current_hp}.")

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.lower().contains("спасибо")
)
async def handle_thanks(message: types.Message):
    """Реагирует на благодарность"""
    if await check_zero_hp(message):
        return
    await message.reply("Всегда пожалуйста! 😊")

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.lower().contains("люблю")
)
async def handle_love(message: types.Message):
    """Реагирует на признание в любви"""
    if await check_zero_hp(message):
        return
    await message.reply("Я тоже вас люблю! ❤️🤡")

@rp_router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.lower().startswith(("список действий", "действия", "рп действия", "список рп"))
)
async def handle_actions_list(message: types.Message):
    """Показывает список всех действий"""
    await show_actions_list(message)

@rp_router.message(
    Command("rp_commands"),
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
)
async def handle_rp_commands(message: types.Message):
    """Обработчик команда /rp_commands"""
    await show_actions_list(message)

async def show_actions_list(message: types.Message):
    """Показывает список RP-действий"""
    if await check_zero_hp(message):
        return
        
    actions_list = "📋 Доступные RP-действия:\n\n"
    for category, actions in Actions.ALL_ACTIONS.items():
        actions_list += f"🔹 {category}:\n"
        actions_list += "\n".join(f"   - {action}" for action in actions)
        actions_list += "\n\n"
    
    await message.reply(actions_list)

# ====================== STATS MODULE ======================

# Создаем отдельный роутер для статистики
# rp_router = Router(name="rp_router")
# rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# Стили оформления
STATS_STYLE = {
    "header": "✨ <b>{sender_username}</b> ✨",
    "divider": "▬▬▬▬▬▬▬▬▬▬▬▬▬",
    "stat_row": "┃ {stat:<15} ┃ {value:>5} ┃",
    "footer": "➖➖➖➖➖➖➖➖➖"
}

class UserActivityTracker:
    def __init__(self):
        self.data = self._load_data()
        self._schedule_daily_reset()
        self.daily_top_users = {}  # Хранит топ пользователей за день
    
    def _load_data(self):
        if os.path.exists(Config.USER_DATA_FILE):
            with open(Config.USER_DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                for user_id, user_data in data.items():
                    if "hp" not in user_data:
                        user_data["hp"] = 0
                    if "daily_flames" not in user_data:
                        user_data["daily_flames"] = 0
                    if "total_flames" not in user_data:
                        user_data["total_flames"] = 0
                return defaultdict(self._default_user_data, data)
        return defaultdict(self._default_user_data)
    
    def _default_user_data(self):
        return {
            "daily_messages": 0,
            "total_messages": 0,
            "last_active": 0,
            "hp": 0,
            "daily_flames": 0,
            "total_flames": 0,
            "daily_top_count": 0
        }
    
    def _schedule_daily_reset(self):
        now = datetime.now()
        midnight = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now > midnight:
            midnight += timedelta(days=1)
        self.next_reset = midnight.timestamp()
    
    def _check_reset(self):
        current_time = time.time()
        if current_time > self.next_reset:
            if self.daily_top_users:
                top_user_id = max(self.daily_top_users, key=self.daily_top_users.get)
                if str(top_user_id) in self.data:
                    self.data[str(top_user_id)]["daily_flames"] += Config.DAILY_TOP_REWARD
                    self.data[str(top_user_id)]["total_flames"] += Config.DAILY_TOP_REWARD
                    self.data[str(top_user_id)]["daily_top_count"] += 1
            
            for user in self.data.values():
                user["daily_messages"] = 0
                user["daily_flames"] = 0
            
            self.daily_top_users = {}
            self._schedule_daily_reset()
            self._save_data()
    
    def _save_data(self):
        with open(Config.USER_DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def _load_hp_data(self):
        hp_data = {}
        if os.path.exists(Config.HP_FILE):
            with open(Config.HP_FILE, "r", encoding='utf-8') as f:
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
        
        if user_id not in self.daily_top_users:
            self.daily_top_users[user_id] = 0
        self.daily_top_users[user_id] += 1
        
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
        self._check_reset()
        users = []
        unique_users = set()
        
        user_list = []
        for user_id, data in self.data.items():
            username = data.get("username", "Неизвестный пользователь")
            user_list.append({
                "username": username,
                "messages": data["daily_messages"],
                "hp": data["hp"],
                "flames": data["total_flames"]
            })

        sorted_users = sorted(user_list, key=lambda x: x["messages"], reverse=True)

        for user in sorted_users:
            if user["username"] in unique_users:
                continue
            
            users.append({
                "name": user["username"],
                "messages": user["messages"],
                "hp": user["hp"],
                "flames": user["flames"]
            })
            unique_users.add(user["username"])
            
            if len(users) >= count:
                break
        
        # Убедимся, что топ содержит от 3 до 10 пользователей
        if len(users) < 3:
            return users[:3] if len(users) >= 3 else users
        return users[:10]

def format_top_message(top_users: list):
    if not top_users:
        return "❌ Нет данных для отображения топа"
    
    message = ["🏆 <b>ИНФО</b> 🏆", STATS_STYLE["divider"]]
    
    for i, user in enumerate(top_users, 1):
        user_name = user.get("name", "Неизвестный пользователь")
        flames = "🔥" * user.get("flames", 0)
        message.append(
            f"{i}. {user_name}: "
            f"✉️ {user.get('messages', 0)} | "
            f"❤️ {user.get('hp', 0)} | "
            f"{flames}"
        )
    
    message.append(STATS_STYLE["footer"])
    return "\n".join(message)

async def show_stats(message: types.Message):
    user = message.from_user
    username = user.username if user.username else user.first_name
    tracker = UserActivityTracker()  # Создаем экземпляр класса
    stats = tracker.get_user_stats(user.id, username)
    
    if not stats:
        await message.reply("❌ Статистика не найдена!")
        return
    
    formatted_stats = format_top_message([{
        "name": username,
        "messages": stats["daily_messages"],
        "hp": stats["hp"],
        "flames": stats["total_flames"]
    }])
    
    await message.reply(formatted_stats, parse_mode="HTML")


@rp_router.message(F.text.lower() == "профиль")
async def show_profile(message: types.Message):
    await show_stats(message)

@rp_router.message(F.text.lower() == "топ")
async def show_top_stats(message: types.Message):
    tracker = UserActivityTracker()  # Создаем экземпляр класса
    top_users = tracker.get_top_users()
    formatted_top = format_top_message(top_users)
    await message.reply(formatted_top, parse_mode="HTML")

@rp_router.message()
async def track_message_activity(message: types.Message):
    user = message.from_user
    username = user.username if user.username else user.first_name
    tracker = UserActivityTracker()  # Создаем экземпляр класса
    tracker.record_activity(user.id, username)

# ====================== НАСТРОЙКА ======================
def setup_rp_handlers(dp):
    """Добавляет RP-роутер в диспетчер"""
    dp.include_router(rp_router)
    return dp


def setup_all_handlers(dp):
    """Добавляет все роутеры в диспетчер"""
    dp = setup_rp_handlers(dp)
    return dp