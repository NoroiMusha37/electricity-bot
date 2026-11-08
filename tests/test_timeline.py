from datetime import date, datetime, time, timedelta

import pytest

from energy_bot.loe.schemas import DaySchedule
from energy_bot.schedule.schemas import OutageBlock
from energy_bot.schedule.timeline import (
    change_to_announce,
    current_block,
    due_warnings,
    is_quiet,
    known_until,
    next_block,
    to_blocks,
)
from tests.conftest import KYIV, make_interval

DAY = date(2026, 11, 10)
NEXT_DAY = date(2026, 11, 11)
CATCHUP = timedelta(minutes=10)


def at(day: date, hh_mm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hh_mm), tzinfo=KYIV)


def schedule(day: date, *periods: tuple[str, str], group: str = "5.1") -> DaySchedule:
    return DaySchedule(date=day, groups={group: [make_interval(start, end) for start, end in periods]})


def block(start: datetime, end: datetime) -> OutageBlock:
    return OutageBlock(start=start, end=end)


def due_at(blocks: list[OutageBlock], now: datetime) -> list[tuple[datetime, int]]:
    return [(warning.block.start, warning.offset_minutes) for warning in due_warnings(blocks, now, [60, 30], CATCHUP)]


def test_blocks_merge_touching_overlapping_and_across_midnight():
    blocks = to_blocks(
        [
            schedule(NEXT_DAY, ("00:00", "02:00"), ("10:00", "11:00")),  # days given out of order
            schedule(
                DAY, ("08:00", "10:00"), ("09:00", "09:30"), ("14:00", "16:00"), ("16:00", "17:30"), ("22:00", "24:00")
            ),
        ],
        "5.1",
        KYIV,
    )
    assert blocks == [
        block(at(DAY, "08:00"), at(DAY, "10:00")),  # overlapping 09:00–09:30 absorbed
        block(at(DAY, "14:00"), at(DAY, "17:30")),  # touching periods joined
        block(at(DAY, "22:00"), at(NEXT_DAY, "02:00")),  # across midnight
        block(at(NEXT_DAY, "10:00"), at(NEXT_DAY, "11:00")),
    ]


def test_blocks_ignore_other_groups():
    assert to_blocks([schedule(DAY, ("08:00", "10:00"), group="1.1")], "5.1", KYIV) == []


def test_blocks_keep_local_wall_clock_on_dst_change():
    dst_end = date(2026, 10, 25)  # clocks go back 04:00 -> 03:00
    [outage] = to_blocks([schedule(dst_end, ("02:00", "05:00"))], "5.1", KYIV)
    assert (outage.start.hour, outage.end.hour) == (2, 5)
    assert (outage.start.utcoffset(), outage.end.utcoffset()) == (timedelta(hours=3), timedelta(hours=2))


def test_known_until_is_midnight_after_last_day_with_the_group():
    schedules = [schedule(DAY, ("08:00", "10:00")), schedule(NEXT_DAY, ("08:00", "09:00"), group="1.1")]
    assert known_until(schedules, "5.1", KYIV) == at(NEXT_DAY, "00:00")  # NEXT_DAY doesn't mention 5.1
    assert known_until(schedules, "1.1", KYIV) == datetime.combine(NEXT_DAY + timedelta(days=1), time(), tzinfo=KYIV)
    assert known_until([], "5.1", KYIV) is None


def test_warning_due_inside_window_only():
    outage = [block(at(DAY, "17:00"), at(DAY, "20:00"))]
    assert due_at(outage, at(DAY, "15:59")) == []
    assert due_at(outage, at(DAY, "16:00")) == [(at(DAY, "17:00"), 60)]
    assert due_at(outage, at(DAY, "16:09")) == [(at(DAY, "17:00"), 60)]  # missed by < catchup, e.g. after a restart
    assert due_at(outage, at(DAY, "16:10")) == []
    assert due_at(outage, at(DAY, "16:30")) == [(at(DAY, "17:00"), 30)]


def test_no_warning_once_outage_started():
    outage = [block(at(DAY, "17:00"), at(DAY, "20:00"))]
    assert due_warnings(outage, at(DAY, "17:05"), [10], CATCHUP) == []  # window 16:50–17:00 is cut at the start


def test_no_warning_for_midnight_continuation():
    blocks = to_blocks([schedule(DAY, ("22:00", "24:00")), schedule(NEXT_DAY, ("00:00", "02:00"))], "5.1", KYIV)
    assert due_warnings(blocks, at(DAY, "23:00"), [60], CATCHUP) == []  # 00:00 is not a new outage


def test_current_and_next_block():
    blocks = [block(at(DAY, "08:00"), at(DAY, "10:00")), block(at(DAY, "14:00"), at(DAY, "16:00"))]
    assert current_block(blocks, at(DAY, "09:00")) == blocks[0]
    assert current_block(blocks, at(DAY, "10:00")) is None  # end is exclusive
    assert next_block(blocks, at(DAY, "09:00")) == blocks[1]
    assert next_block(blocks, at(DAY, "16:00")) is None


def test_change_to_announce():
    old = schedule(DAY, ("17:00", "20:00"))
    assert change_to_announce(old, schedule(DAY, ("17:00", "20:00")), "5.1") is None
    change = change_to_announce(old, schedule(DAY, ("18:00", "21:00")), "5.1")
    assert (change.before[0].label, change.after[0].label) == ("17:00–20:00", "18:00–21:00")
    assert change_to_announce(old, schedule(DAY, ("08:00", "09:00"), group="1.1"), "5.1") is None  # group not in new
    assert change_to_announce(schedule(DAY, group="1.1"), old, "5.1").before == []  # group new in this version


@pytest.mark.parametrize(
    ("now", "start", "end", "expected"),
    [
        ("23:30", "23:00", "07:00", True),
        ("06:59", "23:00", "07:00", True),
        ("07:00", "23:00", "07:00", False),
        ("12:00", "23:00", "07:00", False),
        ("14:00", "13:00", "15:00", True),  # range within one day
        ("15:00", "13:00", "15:00", False),
        ("23:00", "23:00", "23:00", False),  # equal ends: quiet hours off
    ],
)
def test_is_quiet(now, start, end, expected):
    assert is_quiet(at(DAY, now), time.fromisoformat(start), time.fromisoformat(end)) is expected
