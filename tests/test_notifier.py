from datetime import datetime
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage

from energy_bot.monitor.notifier import Notifier
from tests.conftest import KYIV, make_subscriber

DAYTIME, NIGHT = datetime(2026, 11, 10, 15, 0, tzinfo=KYIV), datetime(2026, 11, 10, 23, 30, tzinfo=KYIV)
METHOD = SendMessage(chat_id=1, text="x")


def notifier_with(send_message: AsyncMock) -> tuple[Notifier, AsyncMock]:
    bot, db = AsyncMock(), AsyncMock()
    bot.send_message = send_message
    return Notifier(bot, db), db


async def test_silent_only_during_enabled_quiet_hours():
    send = AsyncMock()
    notifier, _ = notifier_with(send)
    assert await notifier.send_text(make_subscriber(), "day", DAYTIME)
    assert await notifier.send_text(make_subscriber(), "night", NIGHT)
    assert await notifier.send_text(make_subscriber(quiet_enabled=False), "night, quiet off", NIGHT)
    assert [call.kwargs["disable_notification"] for call in send.await_args_list] == [False, True, False]


async def test_rate_limit_is_waited_out_once():
    send = AsyncMock(side_effect=[TelegramRetryAfter(METHOD, "flood", retry_after=0), None])
    notifier, _ = notifier_with(send)
    assert await notifier.send_text(make_subscriber(), "text", DAYTIME)
    assert send.await_count == 2


async def test_blocked_chat_is_deactivated():
    notifier, db = notifier_with(AsyncMock(side_effect=TelegramForbiddenError(METHOD, "blocked")))
    assert not await notifier.send_text(make_subscriber(chat_id=7), "text", DAYTIME)
    db.deactivate.assert_awaited_once_with(7)


async def test_other_errors_report_failure_without_raising():
    notifier, db = notifier_with(AsyncMock(side_effect=TelegramNetworkError(METHOD, "down")))
    assert not await notifier.send_text(make_subscriber(), "text", DAYTIME)
    db.deactivate.assert_not_called()
