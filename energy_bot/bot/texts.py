"""All user-facing texts (Ukrainian) and their formatting."""

from datetime import datetime

from energy_bot.loe.schemas import City
from energy_bot.schedule.schemas import OutageBlock
from energy_bot.storage.schemas import ActiveAccident, Subscriber

COMMANDS = {
    "schedule": "Графік на сьогодні й завтра",
    "status": "Чи є світло зараз",
    "address": "Вказати або змінити адресу",
    "group": "Вказати групу вручну, напр. /group 5.1",
    "quiet": "Тихі години, напр. /quiet 23:00 07:00 або /quiet off",
    "stop": "Відписатися й видалити дані",
}
COMMANDS_LIST = "\n".join(f"/{command} — {description}" for command, description in COMMANDS.items())

START_NEW = (
    "Привіт! Я повідомлятиму про відключення світла від Львівобленерго: зміни графіка, "
    "попередження за 60 і 30 хв до вимкнення та аварійні відключення.\n\n"
    "Почніть із /address, щоб указати адресу.\n\n" + COMMANDS_LIST
)
START_BACK = "З поверненням! Сповіщення знову ввімкнені.\n\n" + COMMANDS_LIST
PRIVATE_BOT = "Цей бот приватний."
ERROR = "Щось пішло не так, спробуйте пізніше."
LOE_UNAVAILABLE = "Сайт Львівобленерго не відповідає, спробуйте ще раз за хвилину."

CANCEL_BUTTON = "Скасувати"
CANCELLED = "Скасовано."
STALE_BUTTON = "Ця кнопка вже не активна. Почніть знову: /address"
ASK_CITY = "Введіть назву населеного пункту, напр. Львів. (/cancel — скасувати)"
ASK_STREET = "Введіть назву вулиці, напр. Городоцька."
ASK_BUILDING = "Введіть номер будинку, напр. 116 або 116а."
NOTHING_FOUND = "Нічого не знайдено, спробуйте написати інакше."
CHOOSE_FROM_LIST = "Оберіть зі списку:"
CHOOSE_GROUP = "Будинок належить до кількох груп. Оберіть свою (перевірити можна на poweron.loe.lviv.ua):"
BUILDING_NOT_FOUND = (
    "Такого будинку не знайдено. Перевірте номер і введіть ще раз, "
    "або вкажіть групу вручну: /group 5.1"
)
NOT_IN_SCHEDULE = "Цей будинок не входить у графік погодинних відключень."

NEED_SUBSCRIPTION = "Спершу вкажіть адресу: /address (або групу: /group 5.1)."
GROUP_USAGE = "Вкажіть групу у форматі /group 5.1 (від 1.1 до 6.2)."
NO_SCHEDULE = "Графік для вашої групи ще не опубліковано."
QUIET_USAGE = "Формат: /quiet 23:00 07:00, /quiet off або /quiet on."
UNKNOWN = "Не розумію. Ось що я вмію:\n\n" + COMMANDS_LIST
STOPPED = "Ваші дані видалено, сповіщень більше не буде. Щоб почати знову — /start."


def city_button(city: City) -> str:
    return f"{city.name} ({city.otg_name})" if city.otg_name else city.name


def address(subscriber: Subscriber) -> str:
    return f"{subscriber.city_name}, {subscriber.street_name} {subscriber.building}"


def saved(subscriber: Subscriber) -> str:
    where = f"Адреса: {address(subscriber)}\n" if subscriber.has_address else ""
    return f"✅ Збережено.\n{where}Група: {subscriber.outage_group}"


def saved_group_only(group: str) -> str:
    return (
        f"✅ Групу {group} збережено.\n"
        "Аварійні відключення повідомляються за адресою, тому для них вкажіть адресу: /address"
    )


def quiet_hours(subscriber: Subscriber) -> str:
    if not subscriber.quiet_enabled:
        return "Тихі години вимкнено: усі сповіщення зі звуком."
    return f"Тихі години: {subscriber.quiet_start:%H:%M}–{subscriber.quiet_end:%H:%M} (сповіщення без звуку)."


def moment(value: datetime, now: datetime) -> str:
    """"17:00" today, "17:00 завтра" tomorrow, "17:00 12.11" otherwise."""
    days_ahead = (value.date() - now.date()).days
    if days_ahead == 0:
        return f"{value:%H:%M}"
    return f"{value:%H:%M} завтра" if days_ahead == 1 else f"{value:%H:%M %d.%m}"


def _until(end: datetime, known_end: datetime, now: datetime) -> str:
    """When power returns; hedged if the outage runs into a day whose schedule isn't published yet."""
    if end < known_end:
        return f"о {moment(end, now)}"
    next_day = "завтра" if (known_end.date() - now.date()).days == 1 else f"{known_end:%d.%m}"
    return f"не раніше {end:%H:%M} (графік на {next_day} ще не опубліковано)"


def status(
        subscriber: Subscriber,
        current: OutageBlock | None,
        upcoming: OutageBlock | None,
        accidents: list[ActiveAccident],
        known_end: datetime | None,
        now: datetime,
) -> str:
    """`known_end` is where schedule knowledge ends (`timeline.known_until`); None or not past today = no data."""
    lines = [
        f"🔴 Аварійне відключення. Орієнтовне відновлення: "
        f"{moment(accident.date_plan_in, now) if accident.date_plan_in else 'невідомо'}."
        for accident in accidents
    ]
    if known_end is None or known_end.date() <= now.date():
        lines.append("Графік на сьогодні ще не опубліковано.")
    else:
        if current is not None:
            mark, schedule = "🔴", f"За графіком світла немає, має з'явитися {_until(current.end, known_end, now)}."
        elif upcoming is not None:
            mark, schedule = "🟢", (
                f"За графіком світло є. Наступне вимкнення о {moment(upcoming.start, now)}, "
                f"світло має з'явитися {_until(upcoming.end, known_end, now)}."
            )
        else:
            mark, schedule = "🟢", "За графіком світло є, відключень не заплановано."
        # During an emergency the schedule line is secondary, so it gets no 🔴/🟢 of its own.
        lines.append(schedule if accidents else f"{mark} {schedule}")
    lines.append("")
    if subscriber.has_address:
        lines.append(f"Адреса: {address(subscriber)}")
    lines.append(f"Група: {subscriber.outage_group}")
    lines.append(quiet_hours(subscriber))
    return "\n".join(lines)
