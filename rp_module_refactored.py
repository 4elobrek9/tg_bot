# rp_module_refactored.py
import asyncio
import time
from datetime import datetime, timedelta
import random
import logging
from typing import Dict, Any, Optional
import aiosqlite
from group_stat import setup_stat_handlers, ProfileManager
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
from aiogram.enums import ParseMode
from group_stat import setup_stat_handlers

# Локальные импорты
import database as db # Используем наш модуль БД

# Импортируем setup_stat_handlers, предполагая, что он существует в group_stat
# !!! Важно: Избегаем `import *` !!!
# Замени 'setup_stat_handlers' и 'group_stat' на реальные имена, если они другие
try:
    # Пытаемся импортировать нужную функцию
    from group_stat import setup_stat_handlers 
    # Если нужны еще функции/классы из group_stat, импортируй их явно здесь
    # from group_stat import some_other_function, SomeStatClass 
    HAS_GROUP_STAT = True
except ImportError:
    logging.warning("Module 'group_stat' or 'setup_stat_handlers' not found. Statistics functionality might be limited.")
    HAS_GROUP_STAT = False
    # Создаем заглушку, если модуль не найден, чтобы код ниже не падал
    def setup_stat_handlers(dp): 
         logging.warning("Stat handlers setup skipped because group_stat module is missing.")
         return dp 


logger = logging.getLogger(__name__) # Используем имя модуля для логгера

# Создаем отдельный роутер для RP
rp_router = Router(name="rp_module")
# Фильтр на тип чата для всех хендлеров этого роутера
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


# ====================== КОНФИГУРАЦИЯ RP ======================
class RPConfig:
    DEFAULT_HP = 100
    MAX_HP = 150
    MIN_HP = 0
    HEAL_COOLDOWN_SECONDS = 1800 # 30 минут в секундах (увеличил для баланса)
    HP_RECOVERY_TIME_SECONDS = 600 # 10 минут в секундах до восстановления после 0 HP
    HP_RECOVERY_AMOUNT = 25 # Количество восстанавливаемого HP (увеличил)
    # DAILY_TOP_REWARD = 1 # Награда за топ дня (если будет функционал топов)


# ====================== ДАННЫЕ ДЕЙСТВИЙ ======================
# Оставляем как есть, это статичные данные
class RPActions:
    # ... (Весь класс RPActions без изменений) ...
    RP_ACTIONS = [
        "ударить", "поцеловать", "обнять", "укусить",
        "погладить", "толкнуть", "ущипнуть", "шлепнуть", "пощечина",
        "пнуть", "схватить", "заплакать", "засмеяться",
        "удивиться", "разозлиться", "испугаться", "подмигнуть", "шепнуть",
        "издеваться"
    ]

    INTIMATE_ACTIONS = {
        "добрые": {
            "поцеловать": {"hp_change_target": +10, "hp_change_sender": +1}, # Лечащий не должен сильно терять HP
            "обнять": {"hp_change_target": +15, "hp_change_sender": +5}, # Обьятия полезны обоим
            "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15}, # Сомнительное действие для HP :)
            "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"hp_change_target": +9, "hp_change_sender": -2}, # Кормящий не должен сильно страдать
            "напоить": {"hp_change_target": +6, "hp_change_sender": -1},
            "сделать массаж": {"hp_change_target": +15, "hp_change_sender": +3}, # Массажист тоже получает удовольствие :)
            "спеть песню": {"hp_change_target": +5, "hp_change_sender": +1},
            "подарить цветы": {"hp_change_target": +12, "hp_change_sender": 0}, # Дарение не должно отнимать HP
            "подрочить": {"hp_change_target": +12, "hp_change_sender": +6}, # Взаимное удовольствие? :)
            "полечить": {"hp_change_target": +25, "hp_change_sender": -5}, # Новое сильное лечащее действие
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
            "успокоить": {"hp_change_target": +5, "hp_change_sender": +1}, # Новое нейтрально-доброе действие
        },
        "злые": {
            "уебать": {"hp_change_target": -20, "hp_change_sender": -2}, # Отдача при сильном ударе
            "схватить за шею": {"hp_change_target": -25, "hp_change_sender": -3}, # Рискованно для атакующего
            "ударить": {"hp_change_target": -10, "hp_change_sender": -1}, # Небольшая отдача
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": -1},
            "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": -1},
            "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"hp_change_target": -80, "hp_change_sender": -10}, # Мощное, но затратное
            "обидеть": {"hp_change_target": -7, "hp_change_sender": 0}, # Новое злое действие
        }
    }

    # Собираем все действия в один словарь для удобного поиска данных
    ALL_ACTION_DATA = {}
    for category_actions in INTIMATE_ACTIONS.values():
        ALL_ACTION_DATA.update(category_actions)

    # Полный список всех команд для парсинга и /rp_commands
    ALL_ACTIONS_LIST_BY_CATEGORY = {
        "Добрые действия ❤️": list(INTIMATE_ACTIONS["добрые"].keys()),
        "Нейтральные действия 😐": list(INTIMATE_ACTIONS["нейтральные"].keys()),
        "Злые действия 💀": list(INTIMATE_ACTIONS["злые"].keys())
    }
    # Множество всех команд для быстрой проверки
    ALL_COMMANDS_SET = set(ALL_ACTION_DATA.keys())


# ====================== Утилиты RP ======================

async def get_user_display_name(user: types.User) -> str:
    """Возвращает имя пользователя для отображения (@username или first_name)."""
    return f"@{user.username}" if user.username else user.full_name # Используем full_name для лучшего отображения

async def update_hp_and_notify(bot: Bot, chat_id: int, user_id: int, hp_change: int, reason: str = "") -> int:
    """Обновляет HP пользователя в БД, проверяет границы и возвращает новое HP."""
    current_stats = await db.get_rp_stats(user_id)
    current_hp = current_stats.get('hp', RPConfig.DEFAULT_HP)
    
    new_hp = max(RPConfig.MIN_HP, min(RPConfig.MAX_HP, current_hp + hp_change))
    
    await db.update_rp_stats(user_id, hp=new_hp)
    
    # Проверяем, не достигло ли HP нуля
    if new_hp <= 0 and current_hp > 0: # Только если HP стало <= 0 в этот раз
        recovery_ts = time.time() + RPConfig.HP_RECOVERY_TIME_SECONDS
        await db.update_rp_stats(user_id, recovery_end_ts=recovery_ts)
        logger.info(f"User {user_id} HP dropped to {new_hp}. Recovery set for {RPConfig.HP_RECOVERY_TIME_SECONDS}s.")
        # Оповещение о потере сознания будет в основном хендлере
    
    return new_hp

def get_command_from_text(text: Optional[str]) -> tuple[Optional[str], str]:
    """Извлекает первую RP-команду и остальной текст."""
    if text is None:
        return None, ""
    text_lower = text.lower()
    # Ищем самое длинное совпадающее действие сначала, чтобы избежать частичных совпадений
    # Например, чтобы "поцеловать в щёчку" нашлось раньше, чем "поцеловать"
    matched_command = None
    for cmd in sorted(RPActions.ALL_COMMANDS_SET, key=len, reverse=True):
        if text_lower.startswith(cmd):
            matched_command = cmd
            break # Нашли самое длинное совпадение

    if matched_command:
        additional_text = text[len(matched_command):].strip()
        return matched_command, additional_text
    else:
        return None, ""

def format_timedelta(seconds: float) -> str:
    """Форматирует секунды в строку 'X мин Y сек'."""
    if seconds <= 0:
        return "готово"
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    secs = total_seconds % 60
    if minutes > 0:
        return f"{minutes} мин {secs} сек"
    else:
        return f"{secs} сек"


# ====================== ПРОВЕРКА СОСТОЯНИЯ ======================

async def check_user_rp_state(message: types.Message) -> bool:
    """
    Проверяет, может ли пользователь выполнять RP действия (HP > 0).
    Отправляет ЛС и удаляет сообщение в группе, если не может.
    Возвращает True, если действие ЗАБЛОКИРОВАНО, False - если разрешено.
    """
    user = message.from_user
    # Убедимся, что пользователь есть в основной таблице users
    await db.ensure_user(user.id, user.username, user.first_name)
    
    stats = await db.get_rp_stats(user.id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_ts = stats.get('recovery_end_ts', 0)
    now = time.time()

    if current_hp <= 0:
        remaining_recovery = recovery_ts - now
        if remaining_recovery > 0:
            time_str = format_timedelta(remaining_recovery)
            try:
                # Отправляем ЛС пользователю
                await message.bot.send_message(
                    user.id,
                    f"Ваше HP равно {current_hp}. Вы пока не можете совершать действия. "
                    f"Автоматическое восстановление {RPConfig.HP_RECOVERY_AMOUNT} HP через {time_str}."
                )
            except TelegramAPIError as e:
                 # Ошибка может быть, если юзер не начал диалог с ботом или заблокировал его
                 logger.warning(f"Could not send RP state notification to user {user.id}: {e.message}")
                 # Можно отправить короткое сообщение в группу, если ЛС не удалось
                 # await message.reply(f"{await get_user_display_name(user)}, вы пока отдыхаете (HP: {current_hp})")
            
            # Удаляем сообщение пользователя в группе
            with suppress(TelegramAPIError): # Игнорируем ошибки при удалении
                await message.delete()
            return True # Действие заблокировано
        else:
             # Время восстановления прошло, но HP еще не восстановлено (случай редкий, но возможный)
             # Восстанавливаем HP прямо здесь
             recovered_hp = await update_hp_and_notify(message.bot, message.chat.id, user.id, RPConfig.HP_RECOVERY_AMOUNT)
             await db.update_rp_stats(user.id, recovery_end_ts=0) # Сбрасываем таймер восстановления
             logger.info(f"User {user.id} HP auto-recovered to {recovered_hp} upon action attempt.")
             try:
                 await message.bot.send_message(user.id, f"Ваше HP восстановлено до {recovered_hp}! Можете действовать.")
             except TelegramAPIError: pass # Игнорим ошибку ЛС
             return False # Действие разрешено после восстановления
             
    return False # HP > 0, действие разрешено


# ====================== ОСНОВНЫЕ ХЭНДЛЕРЫ RP ======================

@rp_router.message(lambda msg: get_command_from_text(msg.text)[0] is not None)
async def handle_rp_action(message: types.Message):
    """Обработчик всех RP-действий, инициируемых текстом."""
    if await check_user_rp_state(message):
        return # Пользователь не может действовать

    if not message.reply_to_message:
        await message.reply("⚠️ Пожалуйста, ответьте на сообщение пользователя, к которому хотите применить действие.")
        return

    command, additional_text = get_command_from_text(message.text)
    if not command: # На всякий случай, хотя lambda фильтр уже проверил
        return

    target_user = message.reply_to_message.from_user
    sender_user = message.from_user

    # Проверка на самого себя
    if target_user.id == sender_user.id:
        await message.reply("🤦 Вы не можете использовать команды на себе!")
        with suppress(TelegramAPIError): await message.delete()
        return
        
    # Проверка на бота (самого себя)
    if target_user.id == message.bot.id:
         await message.reply("🤖 Не трогайте бота! Он вам не игрушка.")
         with suppress(TelegramAPIError): await message.delete()
         return

    # Получаем имена для отображения
    target_name = await get_user_display_name(target_user)
    sender_name = await get_user_display_name(sender_user)
    
    # Убедимся, что оба пользователя есть в БД
    await db.ensure_user(sender_user.id, sender_user.username, sender_user.first_name)
    await db.ensure_user(target_user.id, target_user.username, target_user.first_name)

    action_data = RPActions.ALL_ACTION_DATA.get(command)
    if not action_data: # Если команда как-то прошла фильтр, но данных нет
        logger.warning(f"No action data found for command '{command}' triggered by user {sender_user.id}")
        return 

    # Определяем категорию действия для кулдауна
    action_category = None
    if command in RPActions.INTIMATE_ACTIONS["добрые"]:
        action_category = "добрые"
    elif command in RPActions.INTIMATE_ACTIONS["злые"]:
        action_category = "злые"
    elif command in RPActions.INTIMATE_ACTIONS["нейтральные"]:
         action_category = "нейтральные"

    # --- Проверка кулдауна для лечащих действий ---
    if action_category == "добрые" and action_data.get("hp_change_target", 0) > 0:
        sender_stats = await db.get_rp_stats(sender_user.id)
        heal_cd_ts = sender_stats.get('heal_cooldown_ts', 0)
        now = time.time()
        if now < heal_cd_ts:
            remaining_cd = heal_cd_ts - now
            time_str = format_timedelta(remaining_cd)
            await message.reply(
                f"{sender_name}, лечащие команды можно использовать раз в {format_timedelta(RPConfig.HEAL_COOLDOWN_SECONDS)}. "
                f"Подождите еще {time_str}."
            )
            with suppress(TelegramAPIError): await message.delete()
            return
        else:
             # Устанавливаем новый кулдаун
             new_cd_ts = now + RPConfig.HEAL_COOLDOWN_SECONDS
             await db.update_rp_stats(sender_user.id, heal_cooldown_ts=new_cd_ts)


    # --- Применение изменений HP ---
    hp_change_target = action_data.get("hp_change_target", 0)
    hp_change_sender = action_data.get("hp_change_sender", 0)

    new_target_hp = current_target_hp = (await db.get_rp_stats(target_user.id)).get('hp', RPConfig.DEFAULT_HP)
    new_sender_hp = current_sender_hp = (await db.get_rp_stats(sender_user.id)).get('hp', RPConfig.DEFAULT_HP)


    if hp_change_target != 0:
        new_target_hp = await update_hp_and_notify(message.bot, message.chat.id, target_user.id, hp_change_target)

    if hp_change_sender != 0:
        new_sender_hp = await update_hp_and_notify(message.bot, message.chat.id, sender_user.id, hp_change_sender)

    # --- Формирование ответа ---
    # Простое преобразование в прошедшее время (можно улучшить)
    if command.endswith("ть"):
        command_past = command[:-2] + random.choice(["л", "ла"]) # Добавим случайный род
    elif command.endswith("ться"):
         command_past = command[:-3] + "ся" # Например, "засмеяться" -> "засмеялся"
    else:
        command_past = command # Если не глагол на -ть/-ться

    response_parts = [f"{sender_name} {command_past}"]
    if additional_text:
         response_parts.append(f"{target_name} {additional_text}")
    else:
         response_parts.append(target_name)

    # Добавляем информацию об изменении HP
    hp_info = []
    if hp_change_target > 0:
        hp_info.append(f"{target_name} <b style='color:green;'>+{hp_change_target} HP</b>")
    elif hp_change_target < 0:
        hp_info.append(f"{target_name} <b style='color:red;'>{hp_change_target} HP</b>")

    if hp_change_sender > 0:
        hp_info.append(f"{sender_name} <b style='color:green;'>+{hp_change_sender} HP</b>")
    elif hp_change_sender < 0:
        hp_info.append(f"{sender_name} <b style='color:red;'>{hp_change_sender} HP</b>")
        
    if hp_info:
         response_parts.append(f"({', '.join(hp_info)})")

    # Финальное сообщение об HP
    final_hp_info = []
    if new_target_hp <= 0 and current_target_hp > 0: # Если цель потеряла сознание в этот раз
         final_hp_info.append(f"{target_name} 😵 теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")
    elif hp_change_target != 0: # Показываем HP цели, если оно менялось
         final_hp_info.append(f"HP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}")

    if hp_change_sender != 0: # Показываем HP отправителя, если оно менялось
        final_hp_info.append(f"HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}")
        
    if final_hp_info:
         response_parts.append(f"\n{', '.join(final_hp_info)}")


    response_text = " ".join(response_parts)
    await message.reply(response_text, parse_mode=ParseMode.HTML)

    # Удаляем исходное сообщение с командой
    with suppress(TelegramAPIError):
        await message.delete()

# --- Команды для проверки состояния и информации ---

@rp_router.message(F.text.lower().startswith(("моё хп", "мое хп", "мой хп", "/myhp")))
async def handle_check_hp(message: types.Message):
    """Показывает текущее HP и статус восстановления/кулдауна."""
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)
    
    stats = await db.get_rp_stats(user.id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_ts = stats.get('recovery_end_ts', 0)
    heal_cd_ts = stats.get('heal_cooldown_ts', 0)
    now = time.time()
    
    sender_name = await get_user_display_name(user)
    response_text = f"{sender_name}, ваше HP: <b>{current_hp}/{RPConfig.MAX_HP}</b>"

    # Проверка восстановления
    remaining_recovery = recovery_ts - now
    if remaining_recovery > 0:
        time_str = format_timedelta(remaining_recovery)
        response_text += f"\n<b style='color:orange;'>Восстановление после 0 HP:</b> {RPConfig.HP_RECOVERY_AMOUNT} HP через {time_str}."
    elif current_hp <= 0: # Если HP все еще 0, но время вышло - восстанавливаем
         recovered_hp = await update_hp_and_notify(message.bot, message.chat.id, user.id, RPConfig.HP_RECOVERY_AMOUNT)
         await db.update_rp_stats(user.id, recovery_end_ts=0)
         response_text = f"{sender_name}, ваше HP восстановлено до <b>{recovered_hp}/{RPConfig.MAX_HP}</b>!"
         logger.info(f"User {user.id} HP recovered to {recovered_hp} on /myhp check.")

    # Проверка кулдауна лечения
    remaining_heal_cd = heal_cd_ts - now
    if remaining_heal_cd > 0:
        time_str = format_timedelta(remaining_heal_cd)
        response_text += f"\n<b style='color:blue;'>Кулдаун лечащих действий:</b> {time_str}."

    await message.reply(response_text, parse_mode=ParseMode.HTML)

@rp_router.message(Command("rp_commands"))
@rp_router.message(F.text.lower().startswith(("список действий", "действия", "рп действия", "список рп")))
async def handle_actions_list(message: types.Message):
    """Показывает список всех RP-действий."""
    # Проверка на нулевое HP здесь не нужна, это информационная команда
    actions_list = "<b>📋 Доступные RP-действия:</b>\n\n"
    for category, actions in RPActions.ALL_ACTIONS_LIST_BY_CATEGORY.items():
        actions_list += f"<b>{category}:</b>\n"
        # Делаем команды кликабельными (при ответе на сообщение)
        actions_list += "\n".join(f" `/rp {action}`" for action in actions) # Добавляем префикс /rp
        actions_list += "\n\n"
    actions_list += "<i style='color:gray;'>Чтобы использовать: ответьте на сообщение пользователя и напишите команду (например: /rp поцеловать).</i>"

    await message.reply(actions_list, parse_mode=ParseMode.HTML)

# --- Дополнительные реакции (опционально) ---

# @rp_router.message(F.text.lower().contains("заплакать")) # Убрал отдельный хендлер, т.к. "заплакать" теперь нейтральное действие
# async def handle_cry(message: types.Message): ...

@rp_router.message(F.text.lower().contains("спасибо"))
async def handle_thanks(message: types.Message):
    """Реагирует на благодарность."""
    if await check_user_rp_state(message): return
    await message.reply("Всегда пожалуйста! 😊")

@rp_router.message(F.text.lower().contains("люблю"))
async def handle_love(message: types.Message):
    """Реагирует на признание в любви."""
    if await check_user_rp_state(message): return
    await message.reply("Я тоже вас люблю! ❤️🤡") # Фирменный ответ :)

# --- Фоновая задача для восстановления HP ---
async def periodic_hp_recovery_task(bot: Bot):
     """Периодически проверяет и восстанавливает HP пользователей, у которых оно было 0."""
     logger.info("Periodic HP recovery task started.")
     while True:
         await asyncio.sleep(60) # Проверяем раз в минуту
         now = time.time()
         try:
             async with aiosqlite.connect(db.DB_FILE) as conn:
                 # Находим пользователей, у которых HP <= 0 и время восстановления прошло
                 query = 'SELECT user_id, hp FROM rp_user_stats WHERE hp <= ? AND recovery_end_ts > 0 AND recovery_end_ts <= ?'
                 async with conn.execute(query, (RPConfig.MIN_HP, now)) as cursor:
                     users_to_recover = await cursor.fetchall()

                 if users_to_recover:
                     logger.info(f"Found {len(users_to_recover)} users ready for HP recovery.")
                     for user_id, current_hp in users_to_recover:
                         # Восстанавливаем HP
                         new_hp = min(RPConfig.MAX_HP, current_hp + RPConfig.HP_RECOVERY_AMOUNT)
                         # Обновляем HP и сбрасываем таймер восстановления
                         await conn.execute(
                             'UPDATE rp_user_stats SET hp = ?, recovery_end_ts = 0 WHERE user_id = ?',
                             (new_hp, user_id)
                         )
                         await conn.commit()
                         logger.info(f"User {user_id} HP recovered from {current_hp} to {new_hp}.")
                         
                         # Отправляем уведомление в ЛС
                         user_info = await db.get_user_info(user_id) # Получаем имя пользователя
                         user_name = user_info['first_name'] if user_info else f"Пользователь {user_id}"
                         try:
                             await bot.send_message(
                                 user_id,
                                 f"✅ Ваше HP восстановлено до {new_hp}/{RPConfig.MAX_HP}! Вы снова в строю."
                             )
                         except TelegramAPIError as e:
                             logger.warning(f"Could not send recovery notification to user {user_id}: {e.message}")

         except Exception as e:
             logger.error(f"Error in periodic_hp_recovery_task: {e}", exc_info=True)


# ====================== НАСТРОЙКА ======================
def setup_rp_handlers(dp):
    """Добавляет RP-роутер в главный диспетчер."""
    dp.include_router(rp_router)
    logger.info("RP router included in the main dispatcher.")
    return dp

def setup_all_handlers(dp):
    """Настраивает все хендлеры (RP и Статистику)."""
    dp = setup_rp_handlers(dp)
    logger.info("All handlers configured.")
    return dp

# Добавляем префикс /rp для удобства использования команд в чате
# Теперь можно писать /rp поцеловать @username
@rp_router.message(Command("rp"))
async def handle_rp_command_wrapper(message: types.Message):
     """Обработчик для команд вида /rp <действие> [текст] @упоминание"""
     if not message.reply_to_message:
         # Если нет ответа, проверяем, есть ли упоминание в тексте команды
         command_text = message.text[len("/rp"):].strip()
         entities = message.entities or []
         mentioned_users = [
             entity.user for entity in entities 
             if entity.type == types.MessageEntityType.MENTION or entity.type == types.MessageEntityType.TEXT_MENTION
             if entity.user # Убедимся, что user есть (для text_mention)
         ]
         
         if not mentioned_users:
              await message.reply("⚠️ Используйте команду /rp <действие> [текст], отвечая на сообщение пользователя, или упомяните его (@username).")
              return
              
         # Создаем "псевдо" ответное сообщение для совместимости с основным хендлером
         pseudo_reply = message.model_copy() # Копируем структуру
         pseudo_reply.reply_to_message = types.Message( # Создаем объект Reply
              message_id=0, # Не важно
              date=message.date,
              chat=message.chat,
              from_user=mentioned_users[0] # Берем первого упомянутого
              # Остальные поля можно не заполнять
         )
         pseudo_reply.text = command_text # Текст без /rp
         
         # Вызываем основной обработчик
         await handle_rp_action(pseudo_reply)
         
     else:
          # Если есть ответ, просто убираем /rp и передаем дальше
          message.text = message.text[len("/rp"):].strip()
          await handle_rp_action(message)
