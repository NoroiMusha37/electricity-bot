from aiogram.fsm.state import State, StatesGroup


class AddressForm(StatesGroup):
    city = State()
    street = State()
    building = State()
    group = State()
