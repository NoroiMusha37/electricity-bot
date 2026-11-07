import asyncio
import logging
import re
from collections.abc import Iterable
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ValidationError

from energy_bot.loe.buildings import building_variants
from energy_bot.loe.parser import parse_schedule_html
from energy_bot.loe.schemas import Accident, BuildingAccount, BuildingLookup, City, DaySchedule, MenuItem, Street

logger = logging.getLogger(__name__)

SCHEDULE_API = "https://api.loe.lviv.ua/api"
POWER_API = "https://power-api.loe.lviv.ua/api"
SCHEDULE_ITEM_NAMES = ("Today", "Tomorrow")
USER_AGENT = "energy-bot/0.1 (personal Telegram notifier)"
GROUP_PATTERN = re.compile(r"^\d\.\d$")
RETRY_DELAY_SECONDS = 2

type JsonRecord = dict[str, Any]


class LoeError(Exception):
    """LOE API is unreachable or returned something unexpected."""


def _rank(name: str, query: str) -> tuple[int, int, str]:
    """Sort key: exact match, then prefix match, then substring; shorter names first."""
    name, query = name.casefold(), query.casefold().strip()
    return (0 if name == query else 1 if name.startswith(query) else 2), len(name), name


class LoeClient:
    def __init__(self, tz: ZoneInfo) -> None:
        self._tz = tz
        self._http = httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT})

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get_json(self, url: str, params: dict[str, Any]) -> JsonRecord:
        """GET a JSON object. Network errors, 429 and 5xx get one retry after RETRY_DELAY_SECONDS."""
        for attempt in range(2):
            try:
                response = await self._http.get(url, params=params)
            except httpx.TransportError as exc:
                problem = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code != 429 and response.status_code < 500:
                    break
                problem = f"HTTP {response.status_code}"
            if attempt:
                raise LoeError(f"LOE request to {url} failed twice, last error: {problem}")
            logger.warning(f"LOE request to {url} failed ({problem}), retrying in {RETRY_DELAY_SECONDS}s")
            await asyncio.sleep(RETRY_DELAY_SECONDS)

        if response.status_code != 200:
            raise LoeError(f"LOE returned HTTP {response.status_code} for {url}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise LoeError(f"LOE returned invalid JSON for {url}") from exc
        if not isinstance(payload, dict):
            raise LoeError(f"LOE returned {type(payload).__name__} instead of a JSON object for {url}")
        return payload

    @staticmethod
    def _members(payload: JsonRecord) -> list[Any]:
        """Items of a Hydra collection (`hydra:member`)."""
        members = payload.get("hydra:member")
        if not isinstance(members, list):
            raise LoeError("Unexpected LOE response: no hydra:member list")
        return members

    def _validate_records[T: BaseModel](self, records: Iterable[Any], model: type[T], kind: str) -> list[T]:
        """Validate each record separately: a malformed one is logged and skipped, never hiding the rest."""
        validated = []
        for record in records:
            try:
                validated.append(model.model_validate(record, context={"tz": self._tz}))
            except ValidationError as exc:
                # Field names and reasons only: record contents may be personal data (pw_accounts).
                problems = "; ".join(
                    f"{'.'.join(map(str, error['loc'])) or 'record'}: {error['msg']}" for error in exc.errors()
                )
                logger.warning(f"Skipping malformed LOE {kind} record ({problems})")
        return validated

    async def get_schedules(self) -> list[DaySchedule]:
        """Today's and tomorrow's schedules; days without a published schedule are omitted."""
        payload = await self._get_json(f"{SCHEDULE_API}/menus", {"page": 1, "type": "photo-grafic"})
        try:
            # Only Today/Tomorrow are kept; the large archive item is dropped before validation.
            schedule_items = [
                item for item in payload["hydra:member"][0]["menuItems"] if item.get("name") in SCHEDULE_ITEM_NAMES
            ]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LoeError("Unexpected LOE schedule response format") from exc
        return [
            schedule
            for item in self._validate_records(schedule_items, MenuItem, "menu item")
            if (schedule := parse_schedule_html(item.raw_html, self._tz))
        ]

    async def search_cities(self, text: str) -> list[City]:
        payload = await self._get_json(f"{POWER_API}/pw_cities", {"pagination": "false", "name": text.strip()})
        cities = self._validate_records(self._members(payload), City, "city")
        cities.sort(key=lambda city: _rank(city.name, text))
        return cities

    async def search_streets(self, city_id: int, text: str) -> list[Street]:
        payload = await self._get_json(
            f"{POWER_API}/pw_streets", {"pagination": "false", "city.id": city_id, "name": text.strip()}
        )
        streets = self._validate_records(self._members(payload), Street, "street")
        streets.sort(key=lambda street: _rank(street.name, text))
        return streets

    async def find_groups(self, city_id: int, street_id: int, building: str) -> BuildingLookup:
        """Look up the hourly-schedule group(s) of a building, trying common spellings of its number."""
        for variant in building_variants(building):
            payload = await self._get_json(
                f"{POWER_API}/pw_accounts",
                {"pagination": "false", "city.id": city_id, "street.id": street_id, "buildingName": variant},
            )
            if accounts := self._validate_records(self._members(payload), BuildingAccount, "account"):
                return BuildingLookup(
                    found=True,
                    groups={account.group for account in accounts if GROUP_PATTERN.match(account.group)},
                    building=accounts[0].building_name or variant,
                )
        return BuildingLookup(found=False)

    async def get_accidents(self, city_id: int, street_id: int) -> list[Accident]:
        """Current emergency outages on a street.

        Only the first page (30 records) is read: a single street never has that many at once.
        """
        payload = await self._get_json(f"{POWER_API}/pw_accidents", {"city.id": city_id, "street.id": street_id})
        return self._validate_records(self._members(payload), Accident, "accident")
