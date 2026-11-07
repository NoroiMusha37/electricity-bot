"""Schedule image for one day and one group: a 4×6 grid of hour tiles, each split into two half hours."""

from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from energy_bot.loe.schemas import DaySchedule, Interval
from energy_bot.render import theme
from energy_bot.schedule.timeline import to_blocks

FONTS_DIR = Path(__file__).parent / "fonts"
WIDTH = 1080
SCALE = 2  # Pillow doesn't anti-alias shapes: draw at double size, then downscale for smooth edges

# Layout below is in canvas pixels (final pixels × SCALE).
CANVAS_WIDTH = WIDTH * SCALE
PADDING = 56 * SCALE
GAP = 14 * SCALE
COLUMNS = 4
ROWS = 24 // COLUMNS
TILE_WIDTH = (CANVAS_WIDTH - 2 * PADDING - (COLUMNS - 1) * GAP) // COLUMNS
TILE_HEIGHT = TILE_WIDTH // 2
TILE_RADIUS = 18 * SCALE
LABEL_OFFSET_X, LABEL_OFFSET_Y = 16 * SCALE, 12 * SCALE
RING_GAP, RING_WIDTH = 7 * SCALE, 5 * SCALE
BAR_INSET, BAR_HEIGHT = 14 * SCALE, 6 * SCALE
SUBTITLE_TOP = PADDING + 66 * SCALE
GRID_TOP = PADDING + 150 * SCALE
GRID_BOTTOM = GRID_TOP + ROWS * TILE_HEIGHT + (ROWS - 1) * GAP
FOOTER_TOP = GRID_BOTTOM + 40 * SCALE
FOOTER_SPACING = 26 * SCALE
CHIP_HEIGHT, CHIP_PADDING_X, CHIP_PADDING_Y, CHIP_GAP = 54 * SCALE, 20 * SCALE, 10 * SCALE, 16 * SCALE
PERIODS_LINE_HEIGHT = 38 * SCALE
SWATCH, SWATCH_RADIUS, SWATCH_OUTLINE = 30 * SCALE, 8 * SCALE, 4 * SCALE
LEGEND_TEXT_GAP, LEGEND_ITEM_GAP = 12 * SCALE, 40 * SCALE

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")
PERIODS_SEPARATOR = "  ·  "


def _load_font(file_name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS_DIR / file_name, size * SCALE)


TITLE_FONT = _load_font("Inter-Bold.ttf", 46)
LABEL_FONT = _load_font("Inter-Bold.ttf", 30)
CHIP_FONT = _load_font("Inter-Bold.ttf", 28)
TEXT_FONT = _load_font("Inter-Regular.ttf", 26)
LEGEND_FONT = _load_font("Inter-Regular.ttf", 24)

if LABEL_OFFSET_X + LABEL_FONT.getlength("00:00") > TILE_WIDTH // 2:
    raise RuntimeError("Hour labels must fit inside the tile's first half: their colour follows that half")


def _tile_canvas_box(hour: int) -> tuple[int, int, int, int]:
    row, column = divmod(hour, COLUMNS)
    left, top = PADDING + column * (TILE_WIDTH + GAP), GRID_TOP + row * (TILE_HEIGHT + GAP)
    return left, top, left + TILE_WIDTH, top + TILE_HEIGHT


def tile_box(hour: int) -> tuple[int, int, int, int]:
    """Position (left, top, right, bottom) of an hour's tile in the final image."""
    left, top, right, bottom = _tile_canvas_box(hour)
    return left // SCALE, top // SCALE, right // SCALE, bottom // SCALE


def outages_word(count: int) -> str:
    """Ukrainian plural: 1 вимкнення, 3 вимкнення, 5 вимкнень, 11 вимкнень, 21 вимкнення."""
    return "вимкнень" if count % 10 not in (1, 2, 3, 4) or 11 <= count % 100 <= 14 else "вимкнення"


def format_hours(minutes: int) -> str:
    """Hours with at most one decimal and a Ukrainian decimal comma: 510 -> "8,5", 540 -> "9", 500 -> "8,3"."""
    return f"{round(minutes / 60, 1):g}".replace(".", ",")


def _merged_periods(day: DaySchedule, group: str, now: datetime) -> list[Interval]:
    """The day's outages with touching periods joined (20:00–22:00 + 22:00–24:00 -> 20:00–24:00)."""
    midnight = datetime.combine(day.date, time(), tzinfo=now.tzinfo)
    minute = timedelta(minutes=1)
    return [
        Interval(start_minutes=(block.start - midnight) // minute, end_minutes=(block.end - midnight) // minute)
        for block in to_blocks([day], group, now.tzinfo)
    ]


def _title(day: date, today: date) -> str:
    prefix = {today: "Сьогодні · ", today + timedelta(days=1): "Завтра · "}.get(day, "")
    return f"{prefix}{WEEKDAYS[day.weekday()]} {day:%d.%m}"


def _subtitle(day: DaySchedule, group: str) -> str:
    if day.info_as_of is None:
        return f"Група {group}"
    as_of = f"{day.info_as_of:%H:%M}" if day.info_as_of.date() == day.date else f"{day.info_as_of:%H:%M %d.%m}"
    return f"Група {group} · станом на {as_of}"


def _wrap(items: list[str], font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Join items with separators into as few lines as fit `max_width`."""
    lines: list[str] = []
    for item in items:
        if lines and font.getlength(candidate := f"{lines[-1]}{PERIODS_SEPARATOR}{item}") <= max_width:
            lines[-1] = candidate
        else:
            lines.append(item)
    return lines


def _draw_header(draw: ImageDraw.ImageDraw, day: DaySchedule, group: str, today: date) -> None:
    draw.text((PADDING, PADDING), _title(day.date, today), font=TITLE_FONT, fill=theme.TITLE)
    draw.text((PADDING, SUBTITLE_TOP), _subtitle(day, group), font=TEXT_FONT, fill=theme.SUBTITLE)


def _draw_tiles(draw: ImageDraw.ImageDraw, periods: list[Interval]) -> None:
    # Half-hour slots 0..47 touched by an outage; tile `hour` is made of slots 2*hour and 2*hour + 1.
    off_half_hours = {
        half for period in periods for half in range(period.start_minutes // 30, -(-period.end_minutes // 30))
    }
    for hour in range(24):
        left, top, right, bottom = _tile_canvas_box(hour)
        middle = (left + right) // 2
        first_half_off = 2 * hour in off_half_hours
        draw.rounded_rectangle(
            (left, top, middle, bottom), TILE_RADIUS,
            fill=theme.POWER_OFF if first_half_off else theme.POWER_ON, corners=(True, False, False, True),
        )
        draw.rounded_rectangle(
            (middle, top, right, bottom), TILE_RADIUS,
            fill=theme.POWER_OFF if 2 * hour + 1 in off_half_hours else theme.POWER_ON,
            corners=(False, True, True, False),
        )
        draw.text(
            (left + LABEL_OFFSET_X, top + LABEL_OFFSET_Y), f"{hour:02d}:00", font=LABEL_FONT,
            fill=theme.POWER_OFF_TEXT if first_half_off else theme.POWER_ON_TEXT,
        )


def _draw_current_hour(draw: ImageDraw.ImageDraw, now: datetime) -> None:
    left, top, right, bottom = _tile_canvas_box(now.hour)
    draw.rounded_rectangle(
        (left - RING_GAP, top - RING_GAP, right + RING_GAP, bottom + RING_GAP),
        TILE_RADIUS + RING_GAP, outline=theme.CURRENT_HOUR_RING, width=RING_WIDTH,
    )
    bar_left, bar_right, bar_top = left + BAR_INSET, right - BAR_INSET, bottom - BAR_INSET
    bar_filled = bar_left + (bar_right - bar_left) * now.minute // 60
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_right, bar_top + BAR_HEIGHT), BAR_HEIGHT // 2, fill=theme.PROGRESS_TRACK
    )
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_filled, bar_top + BAR_HEIGHT), BAR_HEIGHT // 2, fill=theme.CURRENT_HOUR_RING
    )


def _draw_chips(draw: ImageDraw.ImageDraw, periods: list[Interval]) -> None:
    total_minutes = sum(period.end_minutes - period.start_minutes for period in periods)
    chips = (
        [f"Без світла {format_hours(total_minutes)} год", f"{len(periods)} {outages_word(len(periods))}"]
        if periods
        else ["Відключень не заплановано"]
    )
    chip_left = PADDING
    for chip in chips:
        chip_right = chip_left + CHIP_FONT.getlength(chip) + 2 * CHIP_PADDING_X
        draw.rounded_rectangle(
            (chip_left, FOOTER_TOP, chip_right, FOOTER_TOP + CHIP_HEIGHT), CHIP_HEIGHT // 2, fill=theme.CHIP_BACKGROUND
        )
        draw.text(
            (chip_left + CHIP_PADDING_X, FOOTER_TOP + CHIP_PADDING_Y), chip, font=CHIP_FONT, fill=theme.CHIP_TEXT
        )
        chip_left = chip_right + CHIP_GAP


def _draw_legend(draw: ImageDraw.ImageDraw, top: int, now: datetime | None) -> None:
    """Swatch + text pairs; the "зараз" item (an outline like the ring) only when `now` is given."""
    items = [(theme.POWER_ON, "є світло"), (theme.POWER_OFF, "немає світла")]
    if now is not None:
        items.append((None, f"зараз {now:%H:%M}"))
    left = PADDING
    for colour, text in items:
        swatch = (left, top, left + SWATCH, top + SWATCH)
        if colour is None:
            draw.rounded_rectangle(swatch, SWATCH_RADIUS, outline=theme.CURRENT_HOUR_RING, width=SWATCH_OUTLINE)
        else:
            draw.rounded_rectangle(swatch, SWATCH_RADIUS, fill=colour)
        text_left = left + SWATCH + LEGEND_TEXT_GAP
        draw.text((text_left, top - SCALE), text, font=LEGEND_FONT, fill=theme.SUBTITLE)
        left = text_left + LEGEND_FONT.getlength(text) + LEGEND_ITEM_GAP


def render_day(day: DaySchedule, group: str, now: datetime) -> bytes:
    """PNG of `group`'s schedule for `day`. `now` is local time; its hour is ringed when `day` is today.

    Raises ValueError if the schedule doesn't mention the group: drawing it as "no outages" would mislead.
    """
    if group not in day.groups:
        raise ValueError(f"Group {group} is not in the schedule for {day.date}")
    periods = _merged_periods(day, group, now)
    period_lines = _wrap([period.label for period in periods], TEXT_FONT, CANVAS_WIDTH - 2 * PADDING)
    periods_top = FOOTER_TOP + CHIP_HEIGHT + FOOTER_SPACING
    legend_top = periods_top + len(period_lines) * PERIODS_LINE_HEIGHT + (FOOTER_SPACING if period_lines else 0)
    is_today = now.date() == day.date

    image = Image.new("RGB", (CANVAS_WIDTH, legend_top + SWATCH + PADDING), theme.BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_header(draw, day, group, now.date())
    _draw_tiles(draw, periods)
    if is_today:
        _draw_current_hour(draw, now)
    _draw_chips(draw, periods)
    for index, line in enumerate(period_lines):
        draw.text((PADDING, periods_top + index * PERIODS_LINE_HEIGHT), line, font=TEXT_FONT, fill=theme.TITLE)
    _draw_legend(draw, legend_top, now if is_today else None)

    buffer = BytesIO()
    image.resize((WIDTH, image.height // SCALE), Image.Resampling.LANCZOS).save(buffer, format="PNG")
    return buffer.getvalue()
