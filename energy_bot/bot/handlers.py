import asyncio
import logging
import re
from datetime import datetime, time
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, ErrorEvent, Message
from aiogram.utils.chat_action import ChatActionSender

from energy_bot.bot import texts
from energy_bot.bot.keyboards import choices_keyboard
from energy_bot.bot.schedule_source import load_schedules
from energy_bot.bot.schemas import CancelChoice, CityChoice, GroupChoice, StreetChoice
from energy_bot.bot.states import AddressForm
from energy_bot.config import settings
from energy_bot.loe.client import LoeClient, LoeError
from energy_bot.loe.schemas import DaySchedule
from energy_bot.render.schedule_image import render_day
from energy_bot.schedule.timeline import current_block, known_until, next_block, to_blocks
from energy_bot.storage.db import Database
from energy_bot.storage.schemas import Subscriber

logger = logging.getLogger(__name__)
router = Router()

GROUP_PATTERN = re.compile(r"^[1-6]\.[12]$")
MAX_CHOICES = 8


def _now() -> datetime:
    return datetime.now(settings.TZ)


def _parse_time(text: str) -> time | None:
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def _new_subscriber(existing: Subscriber | None, chat_id: int, user_id: int, group: str, **address: Any) -> Subscriber:
    """A subscriber with a new group/address; quiet-hour settings are kept from `existing` if there is one."""
    return Subscriber(
        chat_id=chat_id,
        user_id=user_id,
        outage_group=group,
        quiet_start=existing.quiet_start if existing else settings.DEFAULT_QUIET_START,
        quiet_end=existing.quiet_end if existing else settings.DEFAULT_QUIET_END,
        quiet_enabled=existing.quiet_enabled if existing else True,
        **address,
    )


async def _subscriber_or_ask(message: Message, db: Database) -> Subscriber | None:
    """The chat's subscriber; if there is none, asks the user to subscribe first and returns None."""
    if subscriber := await db.get_subscriber(message.chat.id):
        return subscriber
    await message.answer(texts.NEED_SUBSCRIPTION)
    return None


async def _send_schedule(message: Message, subscriber: Subscriber, schedules: list[DaySchedule], now: datetime) -> None:
    days = [day for day in schedules if day.date >= now.date() and subscriber.outage_group in day.groups]
    if not days:
        await message.answer(texts.NO_SCHEDULE)
        return
    async with ChatActionSender.upload_photo(chat_id=message.chat.id, bot=message.bot):
        for day in days:
            png = await asyncio.to_thread(render_day, day, subscriber.outage_group, now)
            await message.answer_photo(BufferedInputFile(png, filename=f"schedule-{day.date}.png"))


async def _save_address(
        message: Message, user_id: int, group: str, state: FSMContext, db: Database, loe: LoeClient
) -> None:
    data = await state.get_data()
    await state.clear()
    subscriber = _new_subscriber(
        await db.get_subscriber(message.chat.id), message.chat.id, user_id, group,
        city_id=data["city_id"], city_name=data["city_name"], otg_name=data["otg_name"],
        street_id=data["street_id"], street_name=data["street_name"], building=data["building"],
    )
    await db.upsert_subscriber(subscriber)
    await db.clear_accidents(message.chat.id)
    await message.answer(texts.saved(subscriber))
    now = _now()
    await _send_schedule(message, subscriber, await load_schedules(db, loe, now), now)


@router.message(CommandStart())
async def start(message: Message, db: Database) -> None:
    subscriber = await db.get_subscriber(message.chat.id)
    if subscriber is None:
        await message.answer(texts.START_NEW)
        return
    await db.upsert_subscriber(subscriber.model_copy(update={"active": True}))
    await message.answer(texts.START_BACK)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELLED)


@router.callback_query(CancelChoice.filter())
async def cancel_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.CANCELLED)
    await callback.answer()


@router.message(Command("address"))
async def ask_city(message: Message, state: FSMContext) -> None:
    await state.set_state(AddressForm.city)
    await message.answer(texts.ASK_CITY)


@router.message(Command("group"))
async def set_group(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    group = (command.args or "").strip()
    if not GROUP_PATTERN.match(group):
        await message.answer(texts.GROUP_USAGE)
        return
    await state.clear()
    existing = await db.get_subscriber(message.chat.id)
    await db.upsert_subscriber(_new_subscriber(existing, message.chat.id, message.from_user.id, group))
    await db.clear_accidents(message.chat.id)
    await message.answer(texts.saved_group_only(group))


@router.message(Command("schedule"))
async def schedule(message: Message, db: Database, loe: LoeClient) -> None:
    if not (subscriber := await _subscriber_or_ask(message, db)):
        return
    now = _now()
    await _send_schedule(message, subscriber, await load_schedules(db, loe, now), now)


@router.message(Command("status"))
async def status(message: Message, db: Database, loe: LoeClient) -> None:
    if not (subscriber := await _subscriber_or_ask(message, db)):
        return
    now = _now()
    async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        schedules = await load_schedules(db, loe, now)
    blocks = to_blocks(schedules, subscriber.outage_group, settings.TZ)
    await message.answer(
        texts.status(
            subscriber, current_block(blocks, now), next_block(blocks, now), await db.active_accidents(message.chat.id),
            known_until(schedules, subscriber.outage_group, settings.TZ), now,
        )
    )


@router.message(Command("quiet"))
async def quiet(message: Message, command: CommandObject, db: Database) -> None:
    if not (subscriber := await _subscriber_or_ask(message, db)):
        return
    match (command.args or "").split():
        case ["off" | "on" as switch]:
            updated = subscriber.model_copy(update={"quiet_enabled": switch == "on"})
        case [start_text, end_text] if (start := _parse_time(start_text)) and (end := _parse_time(end_text)):
            updated = subscriber.model_copy(update={"quiet_start": start, "quiet_end": end, "quiet_enabled": True})
        case _:
            await message.answer(texts.QUIET_USAGE)
            return
    await db.set_quiet_hours(message.chat.id, updated.quiet_start, updated.quiet_end, updated.quiet_enabled)
    await message.answer(texts.quiet_hours(updated))


@router.message(Command("stop"))
async def stop(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await db.delete_subscriber(message.chat.id)
    await message.answer(texts.STOPPED)


@router.message(AddressForm.city, F.text)
async def find_city(message: Message, state: FSMContext, loe: LoeClient) -> None:
    try:
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
            cities = (await loe.search_cities(message.text))[:MAX_CHOICES]
    except LoeError:
        await message.answer(texts.LOE_UNAVAILABLE)
        return
    if not cities:
        await message.answer(texts.NOTHING_FOUND)
        return
    await state.update_data(cities={city.id: city.model_dump() for city in cities})
    await message.answer(
        texts.CHOOSE_FROM_LIST,
        reply_markup=choices_keyboard((texts.city_button(city), CityChoice(city_id=city.id)) for city in cities),
    )


@router.callback_query(AddressForm.city, CityChoice.filter())
async def choose_city(callback: CallbackQuery, callback_data: CityChoice, state: FSMContext) -> None:
    if not (city := ((await state.get_data()).get("cities") or {}).get(callback_data.city_id)):
        await stale_button(callback)
        return
    await state.update_data(cities=None, city_id=city["id"], city_name=city["name"], otg_name=city["otg_name"])
    await state.set_state(AddressForm.street)
    await callback.message.edit_text(f"{city['name']}\n\n{texts.ASK_STREET}")
    await callback.answer()


@router.message(AddressForm.street, F.text)
async def find_street(message: Message, state: FSMContext, loe: LoeClient) -> None:
    try:
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
            streets = (await loe.search_streets((await state.get_data())["city_id"], message.text))[:MAX_CHOICES]
    except LoeError:
        await message.answer(texts.LOE_UNAVAILABLE)
        return
    if not streets:
        await message.answer(texts.NOTHING_FOUND)
        return
    await state.update_data(streets={street.id: street.name for street in streets})
    await message.answer(
        texts.CHOOSE_FROM_LIST,
        reply_markup=choices_keyboard((street.name, StreetChoice(street_id=street.id)) for street in streets),
    )


@router.callback_query(AddressForm.street, StreetChoice.filter())
async def choose_street(callback: CallbackQuery, callback_data: StreetChoice, state: FSMContext) -> None:
    if not (street_name := ((await state.get_data()).get("streets") or {}).get(callback_data.street_id)):
        await stale_button(callback)
        return
    await state.update_data(streets=None, street_id=callback_data.street_id, street_name=street_name)
    await state.set_state(AddressForm.building)
    await callback.message.edit_text(f"{street_name}\n\n{texts.ASK_BUILDING}")
    await callback.answer()


@router.message(AddressForm.building, F.text)
async def find_building(message: Message, state: FSMContext, db: Database, loe: LoeClient) -> None:
    data = await state.get_data()
    try:
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
            lookup = await loe.find_groups(data["city_id"], data["street_id"], message.text)
    except LoeError:
        await message.answer(texts.LOE_UNAVAILABLE)
        return
    if not lookup.found:
        await message.answer(texts.BUILDING_NOT_FOUND)
        return
    if not lookup.groups:
        await state.clear()
        await message.answer(texts.NOT_IN_SCHEDULE)
        return
    await state.update_data(building=lookup.building)
    if len(lookup.groups) == 1:
        await _save_address(message, message.from_user.id, next(iter(lookup.groups)), state, db, loe)
        return
    await state.set_state(AddressForm.group)
    await message.answer(
        texts.CHOOSE_GROUP,
        reply_markup=choices_keyboard((group, GroupChoice(group=group)) for group in sorted(lookup.groups)),
    )


@router.callback_query(AddressForm.group, GroupChoice.filter())
async def choose_group(
        callback: CallbackQuery, callback_data: GroupChoice, state: FSMContext, db: Database, loe: LoeClient
) -> None:
    await callback.message.edit_text(f"Група {callback_data.group}")
    await callback.answer()
    await _save_address(callback.message, callback.from_user.id, callback_data.group, state, db, loe)


@router.message(StateFilter(None))
async def unknown(message: Message) -> None:
    await message.answer(texts.UNKNOWN)


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    """A tap no other handler accepted: a button from a finished or forgotten dialogue (e.g. after a restart)."""
    await callback.answer(texts.STALE_BUTTON, show_alert=True)


@router.errors()
async def on_error(event: ErrorEvent) -> None:
    logger.error(f"Error while handling update {event.update.update_id}", exc_info=event.exception)
    if event.update.message:
        await event.update.message.answer(texts.ERROR)
    elif event.update.callback_query:
        await event.update.callback_query.answer(texts.ERROR, show_alert=True)
