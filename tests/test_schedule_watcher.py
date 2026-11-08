from datetime import date, datetime
from unittest.mock import AsyncMock

from energy_bot.loe.schemas import DaySchedule
from energy_bot.monitor.schedule_watcher import check_schedules
from tests.conftest import KYIV, make_interval, make_subscriber

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=KYIV)
TODAY, TOMORROW = date(2026, 11, 10), date(2026, 11, 11)


def schedule(day: date, group_51: tuple[str, str], group_21: tuple[str, str] = ("08:00", "10:00")) -> DaySchedule:
    return DaySchedule(date=day, groups={"5.1": [make_interval(*group_51)], "2.1": [make_interval(*group_21)]})


def loe_returning(*schedules: DaySchedule) -> AsyncMock:
    loe = AsyncMock()
    loe.get_schedules.return_value = list(schedules)
    return loe


def captions(notifier: AsyncMock) -> list[tuple[int, str]]:
    return [(call.args[0].chat_id, call.args[2]) for call in notifier.send_photo.await_args_list]


async def test_first_run_stores_silently(db):
    await db.upsert_subscriber(make_subscriber())
    notifier = AsyncMock()
    await check_schedules(db, loe_returning(schedule(TODAY, ("17:00", "20:00"))), notifier, NOW)
    notifier.send_photo.assert_not_called()
    assert await db.get_snapshot(TODAY) is not None


async def test_new_day_is_announced_once_per_subscriber_with_one_render_per_group(db):
    await db.save_snapshot(schedule(TODAY, ("17:00", "20:00")))
    for chat_id, group in ((1, "5.1"), (2, "5.1"), (3, "2.1"), (4, "6.2")):
        await db.upsert_subscriber(make_subscriber(chat_id, outage_group=group))
    notifier = AsyncMock()
    loe = loe_returning(schedule(TODAY, ("17:00", "20:00")), schedule(TOMORROW, ("12:00", "14:00")))
    await check_schedules(db, loe, notifier, NOW)
    published = "📅 Опубліковано графік на завтра."
    assert captions(notifier) == [(1, published), (2, published), (3, published)]  # 6.2 isn't in the schedule
    first, second = (call.args[1] for call in notifier.send_photo.await_args_list[:2])
    assert first is second  # rendered once for group 5.1


async def test_change_is_announced_only_to_affected_group(db):
    await db.save_snapshot(schedule(TODAY, ("17:00", "20:00")))
    await db.upsert_subscriber(make_subscriber(1, outage_group="5.1"))
    await db.upsert_subscriber(make_subscriber(2, outage_group="2.1"))
    notifier = AsyncMock()
    await check_schedules(db, loe_returning(schedule(TODAY, ("18:00", "21:00"))), notifier, NOW)
    assert captions(notifier) == [(1, "🔄 Графік на сьогодні змінено.\nБуло: 17:00–20:00\nСтало: 18:00–21:00")]
    assert (await db.get_snapshot(TODAY)).groups["5.1"] == [make_interval("18:00", "21:00")]


async def test_past_day_is_stored_but_not_announced(db):
    yesterday = date(2026, 11, 9)
    await db.save_snapshot(schedule(yesterday, ("17:00", "20:00")))
    await db.upsert_subscriber(make_subscriber())
    notifier = AsyncMock()
    await check_schedules(db, loe_returning(schedule(yesterday, ("18:00", "20:00"))), notifier, NOW)
    notifier.send_photo.assert_not_called()
    assert (await db.get_snapshot(yesterday)).groups["5.1"] == [make_interval("18:00", "20:00")]
