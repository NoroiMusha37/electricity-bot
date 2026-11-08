import logging
from datetime import datetime, timedelta

from energy_bot.loe.client import LoeClient, LoeError
from energy_bot.loe.schemas import DaySchedule
from energy_bot.storage.db import Database

logger = logging.getLogger(__name__)


async def load_schedules(db: Database, loe: LoeClient, now: datetime) -> list[DaySchedule]:
    """Stored schedules from yesterday on. If today's isn't stored yet, today's and tomorrow's come from LOE.

    Fetched schedules are not saved: the schedule watcher is the only writer, so it can still announce them.
    """
    stored = await db.recent_snapshots(now.date() - timedelta(days=1))
    if any(day.date == now.date() for day in stored):
        return stored
    try:
        fetched = await loe.get_schedules()
    except LoeError as exc:
        logger.warning(f"Couldn't fetch schedules for a command: {exc}")
        return stored
    return [day for day in stored if day.date < now.date()] + fetched
