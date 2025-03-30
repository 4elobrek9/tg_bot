from aiogram import Router, types, F
from aiogram.enums import ChatType
import os
import time
from datetime import datetime, timedelta


# ====================== КОНФИГУРАЦИЯ ======================
class Config:
    HP_FILE = "hp.txt"
    COOLDOWN_FILE = "cooldown.txt"
    DEFAULT_HP = 100
    MAX_HP = 100
    MIN_HP = 0
    HEAL_COOLDOWN = 300  # 5 минут в секундах
    HP_RECOVERY_TIME = 600  # 10 минут в секундах
    HP_RECOVERY_AMOUNT = 10


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
            "обнять": {"hp_change_target": +15, "hp_change_sender": -5},
            "погладить": {"hp_change_target": +8, "hp_change_sender": -4},
            "шепнуть": {"hp_change_target": +5, "hp_change_sender": -3},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": -10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
        },
        "злые": {
            "ударить": {"hp_change_target": -10, "hp_change_sender": 0},
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": 0},
        }
    }


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

        # Если HP упал до 0, устанавливаем время восстановления
        if new_hp <= 0 and username not in self.recovery_times:
            self.recovery_times[username] = time.time() + Config.HP_RECOVERY_TIME

    def check_cooldown(self, username):
        """Проверяет, есть ли кулдаун у пользователя"""
        current_time = time.time()
        if username in self.cooldowns and current_time < self.cooldowns[username]:
            return self.cooldowns[username] - current_time
        return 0

    def set_cooldown(self, username):
        """Устанавливает кулдаун для пользователя"""
        self.cooldowns[username] = time.time() + Config.HEAL_COOLDOWN
        self.save_cooldowns()

    def check_hp_recovery(self, username):
        """Проверяет и обновляет HP по таймеру"""
        if username in self.recovery_times:
            current_time = time.time()
            if current_time >= self.recovery_times[username]:
                self.update_user_hp(username, Config.HP_RECOVERY_AMOUNT)
                del self.recovery_times[username]
                return True
        return False

    def get_recovery_time(self, username):
        """Возвращает оставшееся время до восстановления HP"""
        if username in self.recovery_times:
            remaining = self.recovery_times[username] - time.time()
            return max(0, remaining)
        return 0


# ====================== ИНИЦИАЛИЗАЦИЯ ======================
router = Router()
hp_manager = UserHPManager()


# ====================== ХЭНДЛЕРЫ ======================
class Handlers:
    @staticmethod
    async def check_zero_hp(message: types.Message):
        """Проверяет HP пользователя и обрабатывает случай с 0 HP"""
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
                    pass  # Если бот не может писать в ЛС
            await message.delete()
            return True
        return False

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains('заплакать')
    )
    async def handle_cry(message: types.Message):
        """Обработчик плача"""
        if await Handlers.check_zero_hp(message):
            return

        sender = message.from_user
        sender_username = f"@{sender.username}" if sender.username else sender.first_name
        await message.reply(
            f"{sender_username} заплакал. Сейчас будет либо резня, "
            f"либо этот чел просто поплачет и успакоется. "
            f"Надеемся что кто-нибудь похилит {sender_username}\n"
            f"(Довели вы клоуны🤡 бедного {sender_username})"
        )

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().startswith(tuple(
            set(Actions.INTIMATE_ACTIONS["добрые"].keys()) | 
            set(Actions.INTIMATE_ACTIONS["злые"].keys())
        ))
    )
    async def handle_intimate_action(message: types.Message):
        """Обработчик интимных действий"""
        # Проверяем HP отправителя
        if await Handlers.check_zero_hp(message):
            return

        if not message.reply_to_message:
            await message.reply("Пожалуйста, ответьте на сообщение, чтобы использовать эту команду.")
            return

        target_user = message.reply_to_message.from_user
        sender = message.from_user

        # Запрет использования команд на себя
        if target_user.id == sender.id:
            await message.reply("Вы не можете использовать команды на себе!")
            await message.delete()
            return

        target_username = f"@{target_user.username}" if target_user.username else target_user.first_name
        sender_username = f"@{sender.username}" if sender.username else sender.first_name

        # Разбираем команду
        command_parts = message.text.lower().split()
        command = command_parts[0]
        additional_word = " ".join(command_parts[1:]) if len(command_parts) > 1 else ""

        # Проверяем кулдаун для лечащих команд
        if command in Actions.INTIMATE_ACTIONS["добрые"]:
            cooldown_remaining = hp_manager.check_cooldown(sender_username)
            if cooldown_remaining > 0:
                minutes = int(cooldown_remaining // 60)
                seconds = int(cooldown_remaining % 60)
                await message.reply(
                    f"{sender_username}, команды, которые лечат, можно использовать "
                    f"только раз в {Config.HEAL_COOLDOWN//60} минут. "
                    f"Подождите еще {minutes} мин {seconds} сек."
                )
                await message.delete()
                return

        # Формируем глагол в прошедшем времени
        command_past = command[:-2] + "л" if command.endswith("ть") else command

        # Обрабатываем действие
        if command in Actions.INTIMATE_ACTIONS["добрые"]:
            action_data = Actions.INTIMATE_ACTIONS["добрые"][command]
            hp_manager.update_user_hp(target_username, action_data["hp_change_target"])
            hp_manager.update_user_hp(sender_username, action_data["hp_change_sender"])

            # Устанавливаем кулдаун для лечащих команд
            hp_manager.set_cooldown(sender_username)

            response = (
                f"{sender_username} {command_past} {target_username} {additional_word}. "
                f"{target_username} получает +{action_data['hp_change_target']} HP, "
                f"{sender_username} теряет {abs(action_data['hp_change_sender'])} HP."
            )
        elif command in Actions.INTIMATE_ACTIONS["злые"]:
            action_data = Actions.INTIMATE_ACTIONS["злые"][command]
            hp_manager.update_user_hp(target_username, action_data["hp_change_target"])

            # Проверяем, не упало ли HP цели до 0
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

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().startswith("моё хп")
    )
    async def handle_check_hp(message: types.Message):
        """Показывает текущее HP пользователя"""
        if await Handlers.check_zero_hp(message):
            return

        sender = message.from_user
        sender_username = f"@{sender.username}" if sender.username else sender.first_name
        current_hp = hp_manager.get_user_hp(sender_username)

        # Проверяем восстановление HP
        if hp_manager.check_hp_recovery(sender_username):
            current_hp = hp_manager.get_user_hp(sender_username)
            await message.reply(f"{sender_username}, ваше HP было восстановлено на {Config.HP_RECOVERY_AMOUNT}. Текущее HP: {current_hp}.")
        else:
            recovery_time = hp_manager.get_recovery_time(sender_username)
            if recovery_time > 0:
                minutes = int(recovery_time // 60)
                seconds = int(recovery_time % 60)
                await message.reply(
                    f"{sender_username}, ваше текущее HP: {current_hp}. "
                    f"Автоматическое восстановление {Config.HP_RECOVERY_AMOUNT} HP через {minutes} мин {seconds} сек."
                )
            else:
                await message.reply(f"{sender_username}, ваше текущее HP: {current_hp}.")

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains("спасибо")
    )
    async def handle_thanks(message: types.Message):
        """Реагирует на благодарность"""
        if await Handlers.check_zero_hp(message):
            return
        await message.reply("Всегда пожалуйста! 😊")

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains("люблю")
    )
    async def handle_love(message: types.Message):
        """Реагирует на признание в любви"""
        if await Handlers.check_zero_hp(message):
            return
        await message.reply("Я тоже вас люблю! ❤️🤡")

    @staticmethod
    @router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().startswith(("список действий", "действия", "рп действия"))
    )
    async def handle_actions_list(message: types.Message):
        """Показывает список всех RP-действий"""
        if await Handlers.check_zero_hp(message):
            return

        actions_list = "Доступные RP-действия:\n" + \
                       "\n".join(f"- {action}" for action in Actions.RP_ACTIONS)

        await message.reply(actions_list)


# ====================== НАСТРОЙКА ======================
def setup_group_handlers(dp):
    dp.include_router(router)
