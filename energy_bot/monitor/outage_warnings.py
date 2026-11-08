from collections.abc import Sequence
from datetime import datetime, timedelta

from energy_bot.bot import texts
from energy_bot.monitor.notifier import Notifier
from energy_bot.schedule.timeline import due_warnings, known_until, to_blocks
from energy_bot.storage.db import Database


async def send_due_warnings(
        db: Database, notifier: Notifier, offsets_minutes: Sequence[int], catchup: timedelta, now: datetime
) -> None:
    """Send each subscriber the 60/30-minute warnings that are due now, each one exactly once.

    A warning is marked as sent only after delivery, so a failed send is retried on the next tick.
    """
    schedules = await db.recent_snapshots(now.date() - timedelta(days=1))
    for subscriber in await db.active_subscribers():
        blocks = to_blocks(schedules, subscriber.outage_group, now.tzinfo)
        if not (due := due_warnings(blocks, now, offsets_minutes, catchup)):
            continue
        known_end = known_until(schedules, subscriber.outage_group, now.tzinfo)
        for warning in due:
            key = f"warn|{warning.block.start.isoformat()}|{warning.offset_minutes}"
            if await db.is_sent(subscriber.chat_id, key):
                continue
            text = texts.warning(warning.block, known_end, now)
            if await notifier.send_text(subscriber, text, now):
                await db.mark_sent(subscriber.chat_id, key, now)
