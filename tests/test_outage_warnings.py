from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

from energy_bot.loe.schemas import DaySchedule
from energy_bot.monitor.outage_warnings import send_due_warnings
from tests.conftest import KYIV, make_interval, make_subscriber

TODAY = date(2026, 11, 10)
CATCHUP = timedelta(minutes=10)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, tzinfo=KYIV)


async def prepare(db, *periods: tuple[str, str]) -> None:
    await db.save_snapshot(DaySchedule(date=TODAY, groups={"5.1": [make_interval(*period) for period in periods]}))
    await db.upsert_subscriber(make_subscriber())


async def test_warning_is_sent_once_with_return_time(db):
    await prepare(db, ("17:00", "20:00"))
    notifier = AsyncMock()
    notifier.send_text.return_value = True
    await send_due_warnings(db, notifier, [60, 30], CATCHUP, at(16, 0))
    await send_due_warnings(db, notifier, [60, 30], CATCHUP, at(16, 1))  # next tick: already sent
    [call] = notifier.send_text.await_args_list
    assert call.args[1] == "⏰ Через 60 хв (о 17:00) вимкнення світла. Світло має з'явитися о 20:00."


async def test_failed_send_is_retried_on_next_tick(db):
    await prepare(db, ("17:00", "20:00"))
    notifier = AsyncMock()
    notifier.send_text.side_effect = [False, True]
    await send_due_warnings(db, notifier, [30], CATCHUP, at(16, 30))
    await send_due_warnings(db, notifier, [30], CATCHUP, at(16, 31))
    assert notifier.send_text.await_count == 2
    assert notifier.send_text.await_args.args[1].startswith("⏰ Через 29 хв (о 17:00)")  # counted from now


async def test_return_time_is_hedged_when_tomorrow_is_unknown(db):
    await prepare(db, ("22:00", "24:00"))
    notifier = AsyncMock()
    await send_due_warnings(db, notifier, [60], CATCHUP, at(21, 0))
    assert notifier.send_text.await_args.args[1].endswith(
        "Світло має з'явитися не раніше 00:00 (графік на завтра ще не опубліковано)."
    )
