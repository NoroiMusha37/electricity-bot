import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from energy_bot.bot import texts
from energy_bot.bot.handlers import router
from energy_bot.bot.middlewares import AllowListMiddleware
from energy_bot.config import settings
from energy_bot.loe.client import LoeClient
from energy_bot.storage.db import Database


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every request at INFO
    db = await Database.connect(settings.DB_PATH)
    loe = LoeClient(settings.TZ)
    bot = Bot(settings.BOT_TOKEN.get_secret_value())
    dispatcher = Dispatcher(storage=MemoryStorage(), db=db, loe=loe)
    allow_list = AllowListMiddleware(settings.ALLOWED_USER_IDS)
    dispatcher.message.outer_middleware(allow_list)
    dispatcher.callback_query.outer_middleware(allow_list)
    dispatcher.include_router(router)
    try:
        await bot.set_my_commands(
            [BotCommand(command=command, description=description) for command, description in texts.COMMANDS.items()]
        )
        await dispatcher.start_polling(bot)
    finally:
        await loe.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
