from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='324')],
        [KeyboardButton(text='34')],
        [KeyboardButton(text='24')],
        [KeyboardButton(text='32')]
    ],
    resize_keyboard=True,
    input_field_placeholder='выбирай пункт меню сука'
)
