from datetime import date, datetime
from unittest.mock import AsyncMock

from energy_bot.bot.schedule_source import load_schedules
from energy_bot.loe.client import LoeError
from energy_bot.loe.schemas import DaySchedule
from tests.conftest import KYIV

NOW = datetime(2026, 11, 10, 15, 0, tzinfo=KYIV)
YESTERDAY, TODAY, TOMORROW = (DaySchedule(date=date(2026, 11, day), groups={"5.1": []}) for day in (9, 10, 11))


def fakes(stored: list[DaySchedule], fetched: list[DaySchedule] | Exception) -> tuple[AsyncMock, AsyncMock]:
    db = AsyncMock()
    db.recent_snapshots.return_value = stored
    loe = AsyncMock()
    if isinstance(fetched, Exception):
        loe.get_schedules.side_effect = fetched
    else:
        loe.get_schedules.return_value = fetched
    return db, loe


async def test_uses_stored_when_today_is_stored():
    db, loe = fakes([YESTERDAY, TODAY], [])
    assert await load_schedules(db, loe, NOW) == [YESTERDAY, TODAY]
    loe.get_schedules.assert_not_called()


async def test_fetches_without_saving_when_today_is_missing():
    db, loe = fakes([YESTERDAY], [TODAY, TOMORROW])
    assert await load_schedules(db, loe, NOW) == [YESTERDAY, TODAY, TOMORROW]
    db.save_snapshot.assert_not_called()  # the watcher must still see it as new


async def test_falls_back_to_stored_when_loe_fails():
    db, loe = fakes([YESTERDAY], LoeError("down"))
    assert await load_schedules(db, loe, NOW) == [YESTERDAY]
