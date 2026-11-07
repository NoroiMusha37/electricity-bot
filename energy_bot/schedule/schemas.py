from datetime import datetime

from pydantic import BaseModel, ConfigDict

from energy_bot.loe.schemas import Interval


class OutageBlock(BaseModel):
    """A continuous period without power as real, timezone-aware moments; may span midnight."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime


class DueWarning(BaseModel):
    block: OutageBlock
    offset_minutes: int


class GroupChange(BaseModel):
    """A group's outage periods for one day before and after a schedule update."""

    before: list[Interval]
    after: list[Interval]
