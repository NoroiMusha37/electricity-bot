import asyncio
from datetime import datetime

from energy_bot.bot import texts
from energy_bot.loe.client import LoeClient
from energy_bot.loe.schemas import DaySchedule
from energy_bot.monitor.notifier import Notifier
from energy_bot.render.schedule_image import render_day
from energy_bot.schedule.timeline import change_to_announce
from energy_bot.storage.db import Database
from energy_bot.storage.schemas import Subscriber


async def check_schedules(db: Database, loe: LoeClient, notifier: Notifier, now: datetime) -> None:
    """Store the latest schedules and tell subscribers about new days and changes for their group.

    On the very first run (empty database) schedules are stored silently: nothing is "new" to the user yet.
    Past days (LOE may still edit yesterday's schedule after midnight) are stored but never announced.
    """
    schedules = await loe.get_schedules()
    subscribers = await db.active_subscribers() if await db.has_snapshots() else []
    for day in schedules:
        if subscribers and day.date >= now.date():
            await _announce(day, await db.get_snapshot(day.date), subscribers, notifier, now)
        await db.save_snapshot(day)


async def _announce(
        day: DaySchedule, previous: DaySchedule | None, subscribers: list[Subscriber], notifier: Notifier, now: datetime
) -> None:
    images: dict[str, bytes] = {}
    for subscriber in subscribers:
        group = subscriber.outage_group
        if previous is None:
            if group not in day.groups:
                continue
            caption = texts.schedule_published(day.date, now)
        elif change := change_to_announce(previous, day, group):
            caption = texts.schedule_changed(day.date, change, now)
        else:
            continue
        if group not in images:
            images[group] = await asyncio.to_thread(render_day, day, group, now)
        await notifier.send_photo(subscriber, images[group], caption, now)
