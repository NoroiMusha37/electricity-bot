import json
from pathlib import Path
from zoneinfo import ZoneInfo

from energy_bot.loe.schemas import Interval

FIXTURES = Path(__file__).parent / "fixtures"
KYIV = ZoneInfo("Europe/Kyiv")


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> dict:
    return json.loads(fixture_text(name))


def to_minutes(hh_mm: str) -> int:
    return int(hh_mm[:2]) * 60 + int(hh_mm[3:])


def make_interval(start: str, end: str) -> Interval:
    return Interval(start_minutes=to_minutes(start), end_minutes=to_minutes(end))
