"""Parser for the LOE schedule ``rawHtml``.

Example input (one ``<p>`` per line)::

    Графік погодинних відключень на 17.10.2026
    Інформація станом на 18:56 17.10.2026
    Група 1.1. Електроенергії немає з 20:00 до 22:00.
    Група 2.1. Електроенергії немає з 00:00 до 05:30, з 09:00 до 14:00, з 20:00 до 24:00.
    Група 6.2. Електроенергія є.
"""

import html
import logging
import re
from datetime import datetime
from operator import attrgetter
from zoneinfo import ZoneInfo

from energy_bot.loe.schemas import MINUTES_PER_DAY, DaySchedule, Interval

logger = logging.getLogger(__name__)

_LINE_BREAK = re.compile(r"</p>|<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_DATE = re.compile(r"відключень\s+на\s+(\d{2}\.\d{2}\.\d{4})")
_AS_OF = re.compile(r"станом\s+на\s+(\d{1,2}:\d{2})\s+(\d{2}\.\d{2}\.\d{4})")
_GROUP = re.compile(r"^Група\s+(\d\.\d)\.?(.*)$", re.MULTILINE)
_INTERVAL = re.compile(r"з\s+(\d{1,2}):(\d{2})\s+до\s+(\d{1,2}):(\d{2})")


def _to_text(raw: str) -> str:
    """HTML -> plain text with one trimmed, non-empty line per paragraph."""
    lines = html.unescape(_TAG.sub("", _LINE_BREAK.sub("\n", raw))).splitlines()
    return "\n".join(stripped for line in lines if (stripped := line.strip()))


def _parse_intervals(text: str) -> list[Interval]:
    intervals = []
    for start_hour, start_minute, end_hour, end_minute in _INTERVAL.findall(text):
        start = int(start_hour) * 60 + int(start_minute)
        end = int(end_hour) * 60 + int(end_minute)
        if end == 0 and start > 0:  # "до 00:00" used as end of day
            end = MINUTES_PER_DAY
        if start == end:  # "з 00:00 до 00:00" placeholder seen in LOE archives
            continue
        if not (0 <= start < end <= MINUTES_PER_DAY):
            logger.warning(f"Skipping invalid interval {start_hour}:{start_minute}–{end_hour}:{end_minute} in {text!r}")
            continue
        intervals.append(Interval(start_minutes=start, end_minutes=end))
    intervals.sort(key=attrgetter("start_minutes"))
    return intervals


def parse_schedule_html(raw: str, tz: ZoneInfo) -> DaySchedule | None:
    """Parse a schedule; returns None when there is no schedule (empty or unrecognised text)."""
    if not raw or raw.isspace():
        return None
    text = _to_text(raw)

    date_match = _DATE.search(text)
    if not date_match:
        logger.warning(f"Schedule without a date header: {text[:200]!r}")
        return None

    as_of = _AS_OF.search(text)
    groups = {match.group(1): _parse_intervals(match.group(2)) for match in _GROUP.finditer(text)}
    if not groups:
        logger.warning(f"Schedule for {date_match.group(1)} has no groups: {text[:200]!r}")
        return None
    return DaySchedule(
        date=datetime.strptime(date_match.group(1), "%d.%m.%Y").date(),
        info_as_of=(
            datetime.strptime(f"{as_of.group(1)} {as_of.group(2)}", "%H:%M %d.%m.%Y").replace(tzinfo=tz)
            if as_of
            else None
        ),
        groups=groups,
    )
