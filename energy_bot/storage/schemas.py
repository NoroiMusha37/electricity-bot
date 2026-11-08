from datetime import datetime, time

from pydantic import BaseModel


class Subscriber(BaseModel):
    """A chat that receives notifications. Address fields are empty when the group was set manually (/group)."""

    chat_id: int
    user_id: int
    outage_group: str
    city_id: int | None = None
    city_name: str | None = None
    otg_name: str | None = None
    street_id: int | None = None
    street_name: str | None = None
    building: str | None = None
    quiet_start: time
    quiet_end: time
    quiet_enabled: bool = True
    active: bool = True

    @property
    def has_address(self) -> bool:
        """Emergency outages are reported per street and building, so they need a full address."""
        return self.street_id is not None and self.building is not None


class ActiveAccident(BaseModel):
    """An emergency outage the subscriber was already told about."""

    accident_id: int
    date_plan_in: datetime | None = None
