import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from energy_bot.schedule.timeline import is_quiet
from energy_bot.storage.db import Database
from energy_bot.storage.schemas import Subscriber

logger = logging.getLogger(__name__)


class Notifier:
    """Sends notifications to subscribers: silently during their quiet hours, never raising on Telegram errors."""

    def __init__(self, bot: Bot, db: Database) -> None:
        self._bot = bot
        self._db = db

    async def send_text(self, subscriber: Subscriber, text: str, now: datetime) -> bool:
        return await self._send(subscriber, now, self._bot.send_message, text=text)

    async def send_photo(self, subscriber: Subscriber, png: bytes, caption: str, now: datetime) -> bool:
        photo = BufferedInputFile(png, filename="schedule.png")
        return await self._send(subscriber, now, self._bot.send_photo, photo=photo, caption=caption)

    async def _send(
            self, subscriber: Subscriber, now: datetime, method: Callable[..., Awaitable[Any]], **arguments: Any
    ) -> bool:
        """True if delivered. A chat that blocked the bot is deactivated; other errors are logged and retried later."""
        silent = subscriber.quiet_enabled and is_quiet(now, subscriber.quiet_start, subscriber.quiet_end)
        for attempt in range(2):
            try:
                await method(chat_id=subscriber.chat_id, disable_notification=silent, **arguments)
                return True
            except TelegramRetryAfter as exc:
                if attempt:
                    break
                logger.warning(f"Telegram rate limit for chat {subscriber.chat_id}, waiting {exc.retry_after}s")
                await asyncio.sleep(exc.retry_after)
            except TelegramForbiddenError:
                logger.info(f"Chat {subscriber.chat_id} blocked the bot, deactivating it")
                await self._db.deactivate(subscriber.chat_id)
                return False
            except TelegramAPIError as exc:
                logger.warning(f"Couldn't notify chat {subscriber.chat_id}: {exc}")
                return False
        logger.warning(f"Couldn't notify chat {subscriber.chat_id}: still rate-limited")
        return False
