from datetime import time
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_int_list(value: object) -> object:
    """Accept both `123,456` and `[123, 456]` from the environment."""
    if isinstance(value, str):
        value = value.strip().strip("[]")
        return [int(part) for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: SecretStr
    ALLOWED_USER_IDS: Annotated[list[int], NoDecode]

    DB_PATH: str = "energy_bot.db"
    TIMEZONE: str = "Europe/Kyiv"

    SCHEDULE_POLL_SECONDS: int = 300
    ACCIDENT_POLL_SECONDS: int = 180
    WARNING_TICK_SECONDS: int = 60
    WARNING_OFFSETS_MINUTES: Annotated[list[int], NoDecode] = [60, 30]
    WARNING_CATCHUP_MINUTES: int = 10

    DEFAULT_QUIET_START: time = time(23, 0)
    DEFAULT_QUIET_END: time = time(7, 0)

    LOG_LEVEL: str = "INFO"

    _split_lists = field_validator("ALLOWED_USER_IDS", "WARNING_OFFSETS_MINUTES", mode="before")(_parse_int_list)

    @property
    def TZ(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)
