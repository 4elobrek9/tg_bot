from aiogram import types, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from group_chat import UserHPManager
from actions_class import Actions
import time


class Config:
    HP_FILE = "data/hp_data.txt"
    COOLDOWN_FILE = "cooldown.txt"
    USER_DATA_FILE = "data/user_activity.json"
    DEFAULT_HP = 100
    MAX_HP = 150
    MIN_HP = 0
    HEAL_COOLDOWN = 30  # 0.5 минут в секундах
    HP_RECOVERY_TIME = 600  # 10 минут в секундах
    HP_RECOVERY_AMOUNT = 10
    DAILY_TOP_REWARD = 1  # +1 огонёк за топ1 за день


rp_router = Router(name="rp_router")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
hp_manager = UserHPManager


class Handlers:
    @staticmethod
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

    @staticmethod
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

    @staticmethod
    @rp_router.message(
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
            f"либо этот человек просто поплачет и успокоится. "
            f"Надеемся, что кто-нибудь похилит {sender_username}\n"
            f"(Довели вы клоуны🤡 бедного {sender_username})"
        )

    @staticmethod
    @rp_router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        lambda message: Handlers.get_command_from_text(message.text)[0] is not None
    )
    async def handle_intimate_action(message: types.Message):
        """Обработчик RP-действий"""
        if await Handlers.check_zero_hp(message):
            return

        if not message.reply_to_message:
            await message.reply("Пожалуйста, ответьте на сообщение, чтобы использовать эту команду.")
            return

        command, additional_word = Handlers.get_command_from_text(message.text)
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
                f"{sender_username} теряет {abs(action_data['hp_change_sender'])} HP."
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

    @staticmethod
    @rp_router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().startswith(("моё хп", "мое хп", "мой хп"))
    )
    async def handle_check_hp(message: types.Message):
        """Показывает текущее HP"""
        if await Handlers.check_zero_hp(message):
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

    @staticmethod
    @rp_router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains("спасибо")
    )
    async def handle_thanks(message: types.Message):
        """Реагирует на благодарность"""
        if await Handlers.check_zero_hp(message):
            return
        await message.reply("Всегда пожалуйста! 😊")

    @staticmethod
    @rp_router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains("люблю")
    )
    async def handle_love(message: types.Message):
        """Реагирует на признание в любви"""
        if await Handlers.check_zero_hp(message):
            return
        await message.reply("Я тоже вас люблю! ❤️🤡")

    @staticmethod
    @rp_router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().startswith(("список действий", "действия", "рп действия", "список рп"))
    )
    async def handle_actions_list(message: types.Message):
        """Показывает список всех действий"""
        await Handlers.show_actions_list(message)

    @staticmethod
    @rp_router.message(
        Command("rp_commands"),
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP])
    )
    async def handle_rp_commands(message: types.Message):
        """Обработчик команда /rp_commands"""
        await Handlers.show_actions_list(message)

    @staticmethod
    async def show_actions_list(message: types.Message):
        """Показывает список RP-действий"""
        if await Handlers.check_zero_hp(message):
            return

        actions_list = "📋 Доступные RP-действия:\n\n"
        for category, actions in Actions.ALL_ACTIONS.items():
            actions_list += f"🔹 {category}:\n"
            actions_list += "\n".join(f"   - {action}" for action in actions)
            actions_list += "\n\n"

        await message.reply(actions_list)
