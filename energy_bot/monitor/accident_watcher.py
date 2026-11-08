import logging
from collections import defaultdict
from datetime import datetime

from energy_bot.bot import texts
from energy_bot.loe.buildings import building_matches
from energy_bot.loe.client import LoeClient, LoeError
from energy_bot.loe.schemas import Accident
from energy_bot.monitor.notifier import Notifier
from energy_bot.storage.db import Database
from energy_bot.storage.schemas import ActiveAccident, Subscriber

logger = logging.getLogger(__name__)


async def check_accidents(db: Database, loe: LoeClient, notifier: Notifier, now: datetime) -> None:
    """Tell subscribers with an address when an emergency outage there starts, changes its restore time or ends.

    One LOE request per street; a street whose request fails is skipped until the next run.
    """
    by_street: dict[tuple[int, int], list[Subscriber]] = defaultdict(list)
    for subscriber in await db.active_subscribers():
        if subscriber.has_address:
            by_street[(subscriber.city_id, subscriber.street_id)].append(subscriber)
    for (city_id, street_id), subscribers in by_street.items():
        try:
            accidents = await loe.get_accidents(city_id, street_id)
        except LoeError as exc:
            logger.warning(f"Couldn't check accidents for city {city_id}, street {street_id}: {exc}")
            continue
        for subscriber in subscribers:
            await _update_subscriber(subscriber, accidents, db, notifier, now)


async def _update_subscriber(
        subscriber: Subscriber, accidents: list[Accident], db: Database, notifier: Notifier, now: datetime
) -> None:
    """Compare LOE's accidents at the subscriber's building with the ones they were told about.

    The stored state changes only after a message is delivered, so a failed send is retried next run.
    """
    current = {
        accident.id: accident
        for accident in accidents
        if building_matches(subscriber.building, accident.building_names)
    }
    known = {accident.accident_id: accident for accident in await db.active_accidents(subscriber.chat_id)}
    for accident in current.values():
        if accident.id not in known:
            text = texts.accident_started(accident, now)
        elif known[accident.id].date_plan_in != accident.date_plan_in:
            text = texts.accident_plan_changed(accident, now)
        else:
            continue
        if await notifier.send_text(subscriber, text, now):
            await db.save_accident(
                subscriber.chat_id, ActiveAccident(accident_id=accident.id, date_plan_in=accident.date_plan_in)
            )
    for accident_id in known.keys() - current.keys():
        if await notifier.send_text(subscriber, texts.ACCIDENT_ENDED, now):
            await db.remove_accident(subscriber.chat_id, accident_id)
