from datetime import datetime
from unittest.mock import AsyncMock

from energy_bot.loe.client import LoeError
from energy_bot.loe.schemas import Accident
from energy_bot.monitor.accident_watcher import check_accidents
from tests.conftest import KYIV, make_subscriber

NOW = datetime(2026, 11, 10, 15, 0, tzinfo=KYIV)
START, RESTORE, LATER_RESTORE = (datetime(2026, 11, 10, hour, 0, tzinfo=KYIV) for hour in (14, 18, 20))


def accident(accident_id: int = 1, buildings: list[str] | None = None, restore: datetime | None = RESTORE) -> Accident:
    return Accident(id=accident_id, building_names=buildings or [], date_event=START, date_plan_in=restore)


def loe_returning(*accidents: Accident) -> AsyncMock:
    loe = AsyncMock()
    loe.get_accidents.return_value = list(accidents)
    return loe


def sent_notifier() -> AsyncMock:
    notifier = AsyncMock()
    notifier.send_text.return_value = True
    return notifier


def texts_sent(notifier: AsyncMock) -> list[str]:
    return [call.args[1] for call in notifier.send_text.await_args_list]


async def test_start_update_and_end(db):
    await db.upsert_subscriber(make_subscriber())
    notifier = sent_notifier()
    await check_accidents(db, loe_returning(accident()), notifier, NOW)
    await check_accidents(db, loe_returning(accident()), notifier, NOW)  # unchanged: silent
    await check_accidents(db, loe_returning(accident(restore=LATER_RESTORE)), notifier, NOW)
    await check_accidents(db, loe_returning(), notifier, NOW)
    assert texts_sent(notifier) == [
        "⚠️ Аварійне відключення з 14:00. Орієнтовне відновлення: 18:00.",
        "🕑 Аварійне відключення: оновлено час. Орієнтовне відновлення: 20:00.",
        "✅ Аварійне відключення завершено.",
    ]
    assert await db.active_accidents(1) == []


async def test_only_matching_buildings_and_one_request_per_street(db):
    await db.upsert_subscriber(make_subscriber(1, building="116-А"))
    await db.upsert_subscriber(make_subscriber(2, building="171"))
    await db.upsert_subscriber(make_subscriber(3, street_id=None, building=None))  # group only: no address
    loe, notifier = loe_returning(accident(buildings=["116-А", "5"])), sent_notifier()
    await check_accidents(db, loe, notifier, NOW)
    assert [call.args[0].chat_id for call in notifier.send_text.await_args_list] == [1]
    loe.get_accidents.assert_awaited_once_with(693, 12564)


async def test_failed_send_keeps_state_for_retry(db):
    await db.upsert_subscriber(make_subscriber())
    notifier = AsyncMock()
    notifier.send_text.return_value = False
    await check_accidents(db, loe_returning(accident()), notifier, NOW)
    assert await db.active_accidents(1) == []  # not recorded, so it's announced on the next run


async def test_loe_failure_changes_nothing(db):
    await db.upsert_subscriber(make_subscriber())
    await check_accidents(db, loe_returning(accident()), sent_notifier(), NOW)
    loe, notifier = AsyncMock(), sent_notifier()
    loe.get_accidents.side_effect = LoeError("down")
    await check_accidents(db, loe, notifier, NOW)
    notifier.send_text.assert_not_called()  # no false "ended"
    assert len(await db.active_accidents(1)) == 1
