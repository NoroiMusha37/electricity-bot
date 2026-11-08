from datetime import datetime

from energy_bot.bot import texts
from energy_bot.schedule.schemas import OutageBlock
from energy_bot.storage.schemas import ActiveAccident
from tests.conftest import KYIV, make_subscriber

NOW = datetime(2026, 11, 10, 15, 20, tzinfo=KYIV)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=KYIV)


END_OF_TODAY, END_OF_TOMORROW = at(11, 0), at(12, 0)


def test_moment():
    assert texts.moment(at(10, 17), NOW) == "17:00"
    assert texts.moment(at(11, 2), NOW) == "02:00 завтра"
    assert texts.moment(at(12, 9, 30), NOW) == "09:30 12.11"



def test_status_power_off_with_known_end():
    text = texts.status(make_subscriber(), OutageBlock(start=at(10, 14), end=at(11, 2)), None, [], END_OF_TOMORROW, NOW)
    assert text.startswith("🔴 За графіком світла немає, має з'явитися о 02:00 завтра.")
    assert "Адреса: Львів, Городоцька 116-А" in text
    assert "Тихі години: 23:00–07:00" in text


def test_status_hedges_end_when_next_day_is_unknown():
    text = texts.status(make_subscriber(), OutageBlock(start=at(10, 14), end=END_OF_TODAY), None, [], END_OF_TODAY, NOW)
    assert text.startswith(
        "🔴 За графіком світла немає, має з'явитися не раніше 00:00 (графік на завтра ще не опубліковано)."
    )


def test_status_upcoming_outage():
    text = texts.status(make_subscriber(), None, OutageBlock(start=at(10, 20), end=at(10, 22)), [], END_OF_TODAY, NOW)
    assert text.startswith("🟢 За графіком світло є. Наступне вимкнення о 20:00, світло має з'явитися о 22:00.")


def test_status_emergency_comes_first_and_schedule_loses_its_mark():
    accidents = [ActiveAccident(accident_id=1, date_plan_in=at(10, 19, 30)), ActiveAccident(accident_id=2)]
    text = texts.status(make_subscriber(), None, None, accidents, END_OF_TODAY, NOW)
    first, second, schedule = text.splitlines()[:3]
    assert first == "🔴 Аварійне відключення. Орієнтовне відновлення: 19:30."
    assert second == "🔴 Аварійне відключення. Орієнтовне відновлення: невідомо."
    assert schedule == "За графіком світло є, відключень не заплановано."


def test_status_without_todays_schedule_says_so():
    for known_end in (None, at(10, 0)):  # nothing at all, or only yesterday's schedule
        assert texts.status(make_subscriber(), None, None, [], known_end, NOW).startswith(
            "Графік на сьогодні ще не опубліковано."
        )


def test_status_without_address_and_quiet_off():
    manual = make_subscriber(street_id=None, building=None, quiet_enabled=False)
    text = texts.status(manual, None, None, [], END_OF_TODAY, NOW)
    assert "Адреса" not in text
    assert "Тихі години вимкнено" in text


def test_saved_mentions_address_only_when_present():
    assert "Адреса: Львів, Городоцька 116-А" in texts.saved(make_subscriber())
    assert "Адреса" not in texts.saved(make_subscriber(street_id=None, building=None))


def test_day_label_and_empty_periods():
    assert [texts.day_label(at(day, 0).date(), NOW) for day in (10, 11, 12)] == ["сьогодні", "завтра", "чт 12.11"]
    assert texts.periods([]) == "відключень немає"
