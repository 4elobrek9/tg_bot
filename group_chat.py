from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.filters import ChatTypeFilter

router = Router()

@router.message(
    ChatTypeFilter([ChatType.GROUP, ChatType.SUPERGROUP]),
    F.text.lower().contains("яблоко")
)
async def handle_apple_message(message: types.Message):
    # Получаем информацию об отправителе
    sender = message.from_user
    username = f"@{sender.username}" if sender.username else sender.first_name
    
    # Формируем базовый ответ
    response = f"банан {username}"
    
    # Если сообщение является ответом, добавляем ID исходного отправителя
    if message.reply_to_message:
        original_sender = message.reply_to_message.from_user
        response += f" ({original_sender.id})"
    
    # Отправляем ответ
    await message.reply(response)

def setup_group_handlers(dp):
    dp.include_router(router)