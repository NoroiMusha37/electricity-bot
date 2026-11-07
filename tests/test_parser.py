from datetime import date, datetime

import pytest

from energy_bot.loe.parser import parse_schedule_html
from tests.conftest import KYIV, fixture_text, make_interval

ALL_GROUPS = {f"{queue}.{subqueue}" for queue in range(1, 7) for subqueue in (1, 2)}
HEADER = "<p>Графік погодинних відключень на 01.12.2026</p>"


def test_single_interval_schedule():
    day = parse_schedule_html(fixture_text("schedule_single.html"), KYIV)
    assert day.date == date(2026, 10, 17)
    assert day.info_as_of == datetime(2026, 10, 17, 18, 56, tzinfo=KYIV)
    assert set(day.groups) == ALL_GROUPS
    assert day.groups["1.1"] == [make_interval("20:00", "22:00")]
    assert day.groups["6.2"] == []  # "Електроенергія є."


def test_multiple_intervals_and_end_of_day():
    day = parse_schedule_html(fixture_text("schedule_multi.html"), KYIV)
    assert day.groups["2.1"] == [
        make_interval("00:00", "02:00"),
        make_interval("04:00", "10:00"),
        make_interval("10:30", "11:00"),
        make_interval("15:00", "20:00"),
        make_interval("23:00", "24:00"),
    ]
    assert day.groups["1.1"][-1].label == "20:00–24:00"


def test_zero_length_placeholders_are_dropped():
    day = parse_schedule_html(fixture_text("schedule_glitch.html"), KYIV)
    assert day.groups["1.2"] == []  # one "з 00:00 до 00:00"
    assert day.groups["4.2"] == []  # three of them


def test_end_at_midnight_and_invalid_interval(caplog):
    raw = f"{HEADER}<p>Група 3.1. Електроенергії немає з 22:00 до 00:00, з 20:00 до 18:00, з 9:00 до 10:30.</p>"
    day = parse_schedule_html(raw, KYIV)
    assert day.groups["3.1"] == [make_interval("09:00", "10:30"), make_interval("22:00", "24:00")]  # sorted
    assert "Skipping invalid interval 20:00–18:00" in caplog.text


def test_line_breaks_and_missing_as_of():
    raw = "Графік погодинних відключень на 01.12.2026<br/>Група 3.1. Електроенергія є."
    day = parse_schedule_html(raw, KYIV)
    assert day.info_as_of is None
    assert day.groups == {"3.1": []}


@pytest.mark.parametrize(
    "raw",
    [
        "",  # LOE's "no schedule published"
        "   ",
        "<p>Група 1.1. Електроенергія є.</p>",  # groups but no date
        f"{HEADER}<p>Оновлення графіку очікується</p>",  # date but no groups
    ],
)
def test_no_schedule_returns_none(raw):
    assert parse_schedule_html(raw, KYIV) is None
