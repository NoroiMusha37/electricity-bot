import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# energy_bot.config builds `settings` at import; tests must not depend on a developer's .env.
os.environ.setdefault("BOT_TOKEN", "1:test-token")
os.environ.setdefault("ALLOWED_USER_IDS", "1")

from datetime import time  # noqa: E402

import pytest  # noqa: E402

from energy_bot.loe.schemas import Interval  # noqa: E402
from energy_bot.storage.db import Database  # noqa: E402
from energy_bot.storage.schemas import Subscriber  # noqa: E402

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


def make_subscriber(chat_id: int = 1, **changes) -> Subscriber:
    """A subscriber with a full address (Львів, Городоцька 116-А, group 5.1) and quiet hours 23:00–07:00."""
    return Subscriber(
        chat_id=chat_id, user_id=chat_id, outage_group="5.1", city_id=693, city_name="Львів", otg_name="Львівська",
        street_id=12564, street_name="Городоцька", building="116-А", quiet_start=time(23), quiet_end=time(7),
    ).model_copy(update=changes)


@pytest.fixture
async def db(tmp_path):
    database = await Database.connect(str(tmp_path / "test.db"))
    yield database
    await database.close()
