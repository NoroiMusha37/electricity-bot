from collections.abc import Iterable, Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from energy_bot.loe.schemas import DaySchedule
from energy_bot.schedule.schemas import DueWarning, GroupChange, OutageBlock


def to_blocks(schedules: Iterable[DaySchedule], group: str, tz: ZoneInfo) -> list[OutageBlock]:
    """A group's outages across several days as sorted blocks; touching or overlapping periods are merged.

    22:00–24:00 on one day and 00:00–02:00 on the next become a single block ending at 02:00.
    """
    periods: list[tuple[datetime, datetime]] = []
    for day in schedules:
        midnight = datetime.combine(day.date, time(), tzinfo=tz)
        periods.extend(
            (midnight + timedelta(minutes=interval.start_minutes), midnight + timedelta(minutes=interval.end_minutes))
            for interval in day.groups.get(group, [])
        )
    periods.sort()

    blocks: list[OutageBlock] = []
    for start, end in periods:
        if blocks and start <= blocks[-1].end:
            if end > blocks[-1].end:
                blocks[-1] = OutageBlock(start=blocks[-1].start, end=end)
        else:
            blocks.append(OutageBlock(start=start, end=end))
    return blocks


def known_until(schedules: Iterable[DaySchedule], group: str, tz: ZoneInfo) -> datetime | None:
    """End of the last day whose schedule mentions the group (the midnight after it); None if no day does.

    An outage block ending exactly here may continue: the next day's schedule isn't known yet.
    """
    last_day = max((day.date for day in schedules if group in day.groups), default=None)
    return None if last_day is None else datetime.combine(last_day + timedelta(days=1), time(), tzinfo=tz)


def due_warnings(
        blocks: Iterable[OutageBlock], now: datetime, offsets_minutes: Sequence[int], catchup: timedelta
) -> list[DueWarning]:
    """Warnings whose moment (block start minus offset) has come, at most `catchup` ago and before the outage."""
    return [
        DueWarning(block=block, offset_minutes=offset)
        for block in blocks
        for offset in offsets_minutes
        if (warn_at := block.start - timedelta(minutes=offset)) <= now < min(warn_at + catchup, block.start)
    ]


def current_block(blocks: Iterable[OutageBlock], now: datetime) -> OutageBlock | None:
    return next((block for block in blocks if block.start <= now < block.end), None)


def next_block(blocks: Iterable[OutageBlock], now: datetime) -> OutageBlock | None:
    """The first block starting after `now`; `blocks` must be sorted (as `to_blocks` returns them)."""
    return next((block for block in blocks if block.start > now), None)


def change_to_announce(old: DaySchedule, new: DaySchedule, group: str) -> GroupChange | None:
    """The group's change between two versions of one day's schedule, or None if there is nothing to tell the user.

    Nothing to tell: the periods are the same, or `new` doesn't mention the group at all.
    """
    if group not in new.groups:
        return None
    before = old.groups.get(group, [])
    return None if before == new.groups[group] else GroupChange(before=before, after=new.groups[group])


def is_quiet(now: datetime, quiet_start: time, quiet_end: time) -> bool:
    """Whether local `now` is within quiet hours; the range may wrap midnight (23:00–07:00). Equal ends = none."""
    moment = now.time()
    if quiet_start <= quiet_end:
        return quiet_start <= moment < quiet_end
    return moment >= quiet_start or moment < quiet_end
