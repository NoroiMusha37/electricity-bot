from datetime import datetime
from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User

from energy_bot.bot import texts
from energy_bot.bot.middlewares import AllowListMiddleware

ALLOWED, STRANGER = 111, 999


def message_from(user_id: int) -> Message:
    return Message(
        message_id=1, date=datetime(2026, 11, 10), chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test"), text="/status",
    )


def callback_from(user_id: int) -> CallbackQuery:
    return CallbackQuery(
        id="1", from_user=User(id=user_id, is_bot=False, first_name="Test"), chat_instance="1", data="city:1"
    )


async def test_allowed_user_reaches_handler():
    handler = AsyncMock(return_value="handled")
    assert await AllowListMiddleware([ALLOWED])(handler, message_from(ALLOWED), {}) == "handled"


async def test_stranger_is_refused_without_reaching_handler():
    handler = AsyncMock()
    with patch.object(Message, "answer", AsyncMock()) as answer:
        await AllowListMiddleware([ALLOWED])(handler, message_from(STRANGER), {})
    handler.assert_not_called()
    answer.assert_awaited_once_with(texts.PRIVATE_BOT)


async def test_stranger_button_press_is_refused():
    handler = AsyncMock()
    with patch.object(CallbackQuery, "answer", AsyncMock()) as answer:
        await AllowListMiddleware([ALLOWED])(handler, callback_from(STRANGER), {})
    handler.assert_not_called()
    answer.assert_awaited_once_with(texts.PRIVATE_BOT, show_alert=True)
