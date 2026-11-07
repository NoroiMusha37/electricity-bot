from datetime import date, datetime
from io import BytesIO

import pytest
from PIL import Image, ImageColor

from energy_bot.loe.schemas import DaySchedule
from energy_bot.render import theme
from energy_bot.render.schedule_image import WIDTH, format_hours, outages_word, render_day, tile_box
from tests.conftest import KYIV, make_interval

DAY = date(2026, 11, 7)
ON, OFF = ImageColor.getrgb(theme.POWER_ON), ImageColor.getrgb(theme.POWER_OFF)
RING = ImageColor.getrgb(theme.CURRENT_HOUR_RING)


def render(*periods: tuple[str, str], now: datetime) -> Image.Image:
    day = DaySchedule(date=DAY, groups={"5.1": [make_interval(start, end) for start, end in periods]})
    return Image.open(BytesIO(render_day(day, "5.1", now)))


def half_colours(image: Image.Image, hour: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Colours at the centre of the tile's first and second half (below the label)."""
    left, top, right, bottom = tile_box(hour)
    y = (top + 2 * bottom) // 3
    return image.getpixel(((3 * left + right) // 4, y)), image.getpixel(((left + 3 * right) // 4, y))


def has_ring(image: Image.Image, hour: int) -> bool:
    """The ring is ~2.5 px wide after downscaling, so its colour is compared with a small tolerance."""
    left, top, _, bottom = tile_box(hour)
    pixel = image.getpixel((left - 5, (top + bottom) // 2))  # middle of the ring stroke
    return all(abs(channel - expected) <= 8 for channel, expected in zip(pixel, RING))


def test_tiles_show_half_hours():
    image = render(("00:00", "01:00"), ("06:00", "06:30"), ("09:30", "10:00"), ("22:00", "24:00"),
                   now=datetime(2026, 11, 6, 12, 0, tzinfo=KYIV))
    assert image.width == WIDTH
    assert half_colours(image, 0) == (OFF, OFF)
    assert half_colours(image, 1) == (ON, ON)
    assert half_colours(image, 6) == (OFF, ON)
    assert half_colours(image, 9) == (ON, OFF)
    assert half_colours(image, 23) == (OFF, OFF)  # "до 24:00"


def test_current_hour_ringed_only_today():
    periods = (("14:00", "15:30"),)
    today = render(*periods, now=datetime(2026, 11, 7, 15, 20, tzinfo=KYIV))
    assert has_ring(today, 15)
    assert not has_ring(today, 14)
    assert not has_ring(render(*periods, now=datetime(2026, 11, 6, 15, 20, tzinfo=KYIV)), 15)


def test_missing_group_is_refused():
    day = DaySchedule(date=DAY, groups={"1.1": []})
    with pytest.raises(ValueError, match="5.1"):
        render_day(day, "5.1", datetime(2026, 11, 7, 12, 0, tzinfo=KYIV))


def test_no_outages_all_tiles_on():
    image = render(now=datetime(2026, 11, 6, 12, 0, tzinfo=KYIV))
    assert all(half_colours(image, hour) == (ON, ON) for hour in range(24))


@pytest.mark.parametrize(
    ("count", "word"),
    [(1, "вимкнення"), (3, "вимкнення"), (5, "вимкнень"), (11, "вимкнень"), (14, "вимкнень"), (21, "вимкнення")],
)
def test_outages_word(count, word):
    assert outages_word(count) == word


@pytest.mark.parametrize(("minutes", "text"), [(510, "8,5"), (540, "9"), (500, "8,3")])
def test_format_hours(minutes, text):
    assert format_hours(minutes) == text
