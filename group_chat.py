from aiogram import Router, types, F
from aiogram.enums import ChatType
import os

router = Router()

# Список всех доступных действий
RP_ACTIONS = [
    "ударить", "поцеловать", "обнять", "укусить",
    "погладить", "толкнуть", "ущипнуть", "шлепнуть", "пощечина",
    "пнуть", "схватить", "заплакать", "засмеяться",
    "удивиться", "разозлиться", "испугаться", "подмигнуть", "шепнуть"
]

# Интимные действия (добрые и злые)
INTIMATE_ACTIONS = {
    "добрые": {
        "поцеловать": {"hp_change_target": +10, "hp_change_sender": -5},
        "обнять": {"hp_change_target": +15, "hp_change_sender": -5},
        "погладить": {"hp_change_target": +8, "hp_change_sender": -4},
        "шепнуть": {"hp_change_target": +5, "hp_change_sender": -3},
        "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": -10},
        "секс": {"hp_change_target": +30, "hp_change_sender": +15},  # пенис
    },
    "злые": {
        "ударить": {"hp_change_target": -10, "hp_change_sender": 0},
        "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
        "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
        "пощечина": {"hp_change_target": -12, "hp_change_sender": 0},
    }
}

# Словарь для хранения HP яиц пользователей
user_hp = {}

# Файл для сохранения HP яйца
HP_FILE = "hp.txt"

# Функция для загрузки HP яйца из файла
def load_hp():
    if os.path.exists(HP_FILE):
        with open(HP_FILE, "r", encoding="utf-8") as file:
            for line in file:
                username, hp = line.strip().split(": ")
                user_hp[username] = int(hp)

# Функция для сохранения HP яйца в файл
def save_hp():
    with open(HP_FILE, "w", encoding="utf-8") as file:
        for username, hp in user_hp.items():
            file.write(f"{username}: {hp}\n")

# Функция для получения текущего HP яйца пользователя
def get_user_hp(username):
    if username not in user_hp:
        user_hp[username] = 100  # Начальное значение HP яйца
    return user_hp[username]

# Функция для изменения HP пользователя
def update_user_hp(username, hp_change):
    current_hp = get_user_hp(username)
    new_hp = max(0, min(100, current_hp + hp_change))  # Ограничение HP от 0 до 100
    user_hp[username] = new_hp
    save_hp()

# Плакса
@router.message(
        F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
        F.text.lower().contains('залакать')
)
async def cry(message: types.Message):
    sender = message.from_user
    sender_username = f"@{sender.username}" if sender.username else sender.first_name
    await message.reply(f"{sender_username} залакал. Сейчас будет либо резня, либо этот чел просто поплачет и успакоется. Надеемся что кто-нибудь почилит {sender_username}\n(Довели вы клоуны🤡 бедного челобрека)")


# Обработчик для интимных действий
@router.message(
    F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
    F.text.lower().startswith(tuple(set(INTIMATE_ACTIONS["добрые"].keys()) | set(INTIMATE_ACTIONS["злые"].keys())))
)
async def handle_intimate_action(message: types.Message):
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_username = f"@{target_user.username}" if target_user.username else target_user.first_name
        
        sender = message.from_user
        sender_username = f"@{sender.username}" if sender.username else sender.first_name
        
        # Разделяем текст на команду и дополнительное слово
        command_parts = message.text.lower().split()
        command = command_parts[0]
        additional_word = " ".join(command_parts[1:]) if len(command_parts) > 1 else ""
        
        # Преобразуем команду в прошедшее время
        if command.endswith("ть"):
            command_past = command[:-2] + "л"  # Убираем "ть" и добавляем "л"
        else:
            command_past = command  # Если команда не оканчивается на "ть", оставляем как есть
        
        if command in INTIMATE_ACTIONS["добрые"]:
            action_data = INTIMATE_ACTIONS["добрые"][command]
            update_user_hp(target_username, action_data["hp_change_target"])
            update_user_hp(sender_username, action_data["hp_change_sender"])
            response = f"{sender_username} {command_past} {target_username} {additional_word}. {target_username} получает +{action_data['hp_change_target']} HP, {sender_username} теряет {abs(action_data['hp_change_sender'])} HP."
        elif command in INTIMATE_ACTIONS["злые"]:
            action_data = INTIMATE_ACTIONS["злые"][command]
            update_user_hp(target_username, action_data["hp_change_target"])
            response = f"{sender_username} {command_past} {target_username} {additional_word}. У {target_username} осталось {get_user_hp(target_username)} HP."
        
        await message.reply(response)
        await message.delete()
    else:
        await message.reply("Пожалуйста, ответьте на сообщение, чтобы использовать эту команду.")

# Команда для проверки текущего HP
@router.message(
    F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
    F.text.lower().startswith("моё хп")
)
async def check_hp_command(message: types.Message):
    sender = message.from_user
    sender_username = f"@{sender.username}" if sender.username else sender.first_name
    current_hp = get_user_hp(sender_username)
    await message.reply(f"{sender_username}, ваше текущее HP: {current_hp}.")

# Интерактивные ответы
@router.message(
    F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
    F.text.lower().contains("спасибо")
)
async def interactive_thanks(message: types.Message):
    await message.reply("Всегда пожалуйста! 😊")

@router.message(
    F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]),
    F.text.lower().contains("люблю")
)
async def interactive_love(message: types.Message):
    await message.reply("Я тоже вас люблю! ❤️🤡")

def setup_group_handlers(dp):
    dp.include_router(router)
