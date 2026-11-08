from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from energy_bot.bot import texts
from energy_bot.bot.schemas import CancelChoice


def choices_keyboard(choices: Iterable[tuple[str, CallbackData]]) -> InlineKeyboardMarkup:
    """One button per row, plus a cancel button."""
    builder = InlineKeyboardBuilder()
    for label, callback_data in choices:
        builder.button(text=label, callback_data=callback_data)
    builder.button(text=texts.CANCEL_BUTTON, callback_data=CancelChoice())
    builder.adjust(1)
    return builder.as_markup()
