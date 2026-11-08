from datetime import date, datetime, time

from energy_bot.loe.schemas import DaySchedule
from energy_bot.storage.schemas import ActiveAccident
from tests.conftest import KYIV, make_interval, make_subscriber

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=KYIV)


def schedule(day: date, start: str = "17:00", end: str = "20:00") -> DaySchedule:
    return DaySchedule(date=day, groups={"5.1": [make_interval(start, end)]})


async def test_subscriber_round_trip_and_update(db):
    await db.upsert_subscriber(make_subscriber())
    assert await db.get_subscriber(1) == make_subscriber()
    manual = make_subscriber(outage_group="2.1", city_id=None, street_id=None, building=None)
    await db.upsert_subscriber(manual)
    stored = await db.get_subscriber(1)
    assert stored == manual and not stored.has_address
    assert await db.get_subscriber(2) is None


async def test_quiet_hours_and_deactivate(db):
    await db.upsert_subscriber(make_subscriber(1))
    await db.upsert_subscriber(make_subscriber(2))
    await db.set_quiet_hours(1, time(22, 30), time(6), enabled=False)
    await db.deactivate(2)
    [active] = await db.active_subscribers()
    assert active.chat_id == 1
    assert (active.quiet_start, active.quiet_end, active.quiet_enabled) == (time(22, 30), time(6), False)


async def test_delete_subscriber_removes_related_rows(db):
    await db.upsert_subscriber(make_subscriber())
    await db.mark_sent(1, "warn|x|60", NOW)
    await db.save_accident(1, ActiveAccident(accident_id=7))
    await db.delete_subscriber(1)
    assert await db.get_subscriber(1) is None
    assert not await db.is_sent(1, "warn|x|60")
    assert await db.active_accidents(1) == []


async def test_snapshots(db):
    assert not await db.has_snapshots()
    await db.save_snapshot(schedule(date(2026, 11, 9)))
    await db.save_snapshot(schedule(date(2026, 11, 10)))
    await db.save_snapshot(schedule(date(2026, 11, 10), "18:00", "21:00"))  # newer version replaces
    assert await db.has_snapshots()
    assert await db.get_snapshot(date(2026, 11, 10)) == schedule(date(2026, 11, 10), "18:00", "21:00")
    assert await db.get_snapshot(date(2026, 11, 11)) is None
    assert [day.date for day in await db.recent_snapshots(date(2026, 11, 10))] == [date(2026, 11, 10)]


async def test_sent_notifications_are_per_chat(db):
    await db.mark_sent(1, "warn|x|60", NOW)
    await db.mark_sent(1, "warn|x|60", NOW)  # repeated mark is harmless
    assert await db.is_sent(1, "warn|x|60")
    assert not await db.is_sent(2, "warn|x|60")


async def test_accidents_save_update_remove(db):
    restore = datetime(2026, 11, 10, 19, 30, tzinfo=KYIV)
    await db.save_accident(1, ActiveAccident(accident_id=7))
    await db.save_accident(1, ActiveAccident(accident_id=7, date_plan_in=restore))  # update, not duplicate
    await db.save_accident(2, ActiveAccident(accident_id=8))
    assert await db.active_accidents(1) == [ActiveAccident(accident_id=7, date_plan_in=restore)]
    await db.remove_accident(1, 7)
    assert await db.active_accidents(1) == []
    assert len(await db.active_accidents(2)) == 1
    await db.save_accident(2, ActiveAccident(accident_id=9))
    await db.clear_accidents(2)
    assert await db.active_accidents(2) == []


async def test_prune_drops_only_old_records(db):
    await db.save_snapshot(schedule(date(2026, 11, 2)))  # 8 days old
    await db.save_snapshot(schedule(date(2026, 11, 3)))  # 7 days old: kept
    await db.mark_sent(1, "old", datetime(2026, 11, 6, 11, 0, tzinfo=KYIV))
    await db.mark_sent(1, "recent", datetime(2026, 11, 8, 12, 0, tzinfo=KYIV))
    await db.prune(NOW)
    assert [day.date for day in await db.recent_snapshots(date(2026, 1, 1))] == [date(2026, 11, 3)]
    assert not await db.is_sent(1, "old") and await db.is_sent(1, "recent")
