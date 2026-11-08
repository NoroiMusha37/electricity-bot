from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from energy_bot.bot import texts


class AllowListMiddleware(BaseMiddleware):
    """Lets only allowed Telegram users reach the handlers; everyone else gets a short refusal."""

    def __init__(self, allowed_user_ids: Iterable[int]) -> None:
        self._allowed = frozenset(allowed_user_ids)

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None and user.id in self._allowed:
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(texts.PRIVATE_BOT)
        elif isinstance(event, CallbackQuery):
            await event.answer(texts.PRIVATE_BOT, show_alert=True)
        return None
