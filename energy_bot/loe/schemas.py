from datetime import date, datetime
from typing import Annotated

from pydantic import (
    AliasPath,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from energy_bot.loe.buildings import parse_building_names

MINUTES_PER_DAY = 24 * 60


def _empty_if_none(value: object) -> object:
    return value or ""


EmptyIfNone = Annotated[str, BeforeValidator(_empty_if_none)]


def format_minutes(minutes: int) -> str:
    """Format minutes since midnight as HH:MM (1440 -> "24:00")."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class Interval(BaseModel):
    """Outage period within one day, in minutes since midnight. End is exclusive; 1440 means 24:00."""

    model_config = ConfigDict(frozen=True)

    start_minutes: int = Field(ge=0, lt=MINUTES_PER_DAY)
    end_minutes: int = Field(gt=0, le=MINUTES_PER_DAY)

    @model_validator(mode="after")
    def _check_order(self) -> "Interval":
        if self.end_minutes <= self.start_minutes:
            raise ValueError("interval end must be after start")
        return self

    @property
    def label(self) -> str:
        return f"{format_minutes(self.start_minutes)}–{format_minutes(self.end_minutes)}"


class DaySchedule(BaseModel):
    """Parsed hourly outage schedule (ГПВ) for one day. A group with an empty list has no outages."""

    date: date
    info_as_of: datetime | None = None
    groups: dict[str, list[Interval]]


class MenuItem(BaseModel):
    name: str
    raw_html: str = Field(default="", alias="rawHtml")


class City(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    name: str
    otg_id: int | None = Field(default=None, validation_alias=AliasPath("otg", "@id"))
    otg_name: EmptyIfNone = Field(default="", validation_alias=AliasPath("otg", "name"))

    @field_validator("otg_id", mode="before")
    @classmethod
    def _id_from_iri(cls, iri: object) -> object:
        """LOE links the community by IRI: "/api/pw_otgs/28" -> 28."""
        if isinstance(iri, str):
            tail = iri.rstrip("/").rsplit("/", 1)[-1]
            return int(tail) if tail.isdigit() else None
        return iri


class Street(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    name: str


class BuildingAccount(BaseModel):
    """One `pw_accounts` record. Only these two fields are ever read: the rest may be personal data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    building_name: EmptyIfNone = Field(default="", validation_alias="buildingName")
    group: EmptyIfNone = Field(default="", validation_alias="chergGpv")


class BuildingLookup(BaseModel):
    """Result of a building -> group lookup.

    `found` is False when LOE has no such building; `groups` is empty when the building exists
    but is not part of the hourly schedule ("Не входить"). `building` is the spelling LOE uses
    for the matched building (e.g. "116-А" for user input "116а"); None when not found.
    """

    found: bool
    groups: set[str] = set()
    building: str | None = None


class Accident(BaseModel):
    """Emergency outage (аварійне відключення) on a street.

    Validate with ``context={"tz": ZoneInfo(...)}`` so dates without an offset get local time.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    city_id: int | None = Field(default=None, validation_alias=AliasPath("city", "id"))
    street_id: int | None = Field(default=None, validation_alias=AliasPath("street", "id"))
    building_names: list[str] = Field(default=[], validation_alias="buildingNames")  # empty = whole street
    date_event: datetime = Field(validation_alias="dateEvent")
    date_plan_in: datetime | None = Field(default=None, validation_alias="datePlanIn")
    type_off: int | None = Field(default=None, validation_alias="typeOff")
    comment: EmptyIfNone = Field(default="", validation_alias="koment")

    @field_validator("building_names", mode="before")
    @classmethod
    def _split_building_names(cls, value: object) -> object:
        """"5, 9, 30-а" -> ["5", "9", "30-А"]."""
        return parse_building_names(value) if value is None or isinstance(value, str) else value

    @field_validator("date_plan_in", mode="before")
    @classmethod
    def _none_if_empty(cls, value: object) -> object:
        return value or None

    @field_validator("date_event", "date_plan_in")
    @classmethod
    def _local_time_if_naive(cls, value: datetime | None, info: ValidationInfo) -> datetime | None:
        if value is None or value.tzinfo:
            return value
        tz = (info.context or {}).get("tz")
        if tz is None:
            raise ValueError("date without UTC offset and no 'tz' in validation context")
        return value.replace(tzinfo=tz)
