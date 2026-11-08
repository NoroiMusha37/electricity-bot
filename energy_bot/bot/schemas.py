from aiogram.filters.callback_data import CallbackData


class CityChoice(CallbackData, prefix="city"):
    city_id: int


class StreetChoice(CallbackData, prefix="street"):
    street_id: int


class GroupChoice(CallbackData, prefix="group"):
    group: str


class CancelChoice(CallbackData, prefix="cancel"):
    pass
