import asyncio
import logging
from datetime import timedelta
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from energy_bot.bot import texts
from energy_bot.bot.handlers import router
from energy_bot.bot.middlewares import AllowListMiddleware
from energy_bot.config import settings
from energy_bot.loe.client import LoeClient
from energy_bot.monitor.accident_watcher import check_accidents
from energy_bot.monitor.notifier import Notifier
from energy_bot.monitor.outage_warnings import send_due_warnings
from energy_bot.monitor.runner import run_forever
from energy_bot.monitor.schedule_watcher import check_schedules
from energy_bot.storage.db import Database

PRUNE_INTERVAL_SECONDS = 24 * 60 * 60


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every request at INFO
    db = await Database.connect(settings.DB_PATH)
    loe = LoeClient(settings.TZ)
    bot = Bot(settings.BOT_TOKEN.get_secret_value())
    notifier = Notifier(bot, db)
    dispatcher = Dispatcher(storage=MemoryStorage(), db=db, loe=loe)
    allow_list = AllowListMiddleware(settings.ALLOWED_USER_IDS)
    dispatcher.message.outer_middleware(allow_list)
    dispatcher.callback_query.outer_middleware(allow_list)
    dispatcher.include_router(router)
    catchup = timedelta(minutes=settings.WARNING_CATCHUP_MINUTES)
    monitors = [
        asyncio.create_task(
            run_forever(
                "schedule watcher", settings.SCHEDULE_POLL_SECONDS, partial(check_schedules, db, loe, notifier),
                settings.TZ,
            )
        ),
        asyncio.create_task(
            run_forever(
                "accident watcher", settings.ACCIDENT_POLL_SECONDS, partial(check_accidents, db, loe, notifier),
                settings.TZ,
            )
        ),
        asyncio.create_task(
            run_forever(
                "outage warnings", settings.WARNING_TICK_SECONDS,
                partial(send_due_warnings, db, notifier, settings.WARNING_OFFSETS_MINUTES, catchup), settings.TZ,
            )
        ),
        asyncio.create_task(run_forever("database prune", PRUNE_INTERVAL_SECONDS, db.prune, settings.TZ)),
    ]
    try:
        await bot.set_my_commands(
            [BotCommand(command=command, description=description) for command, description in texts.COMMANDS.items()]
        )
        # The bot session is closed below, after the monitors, so none of them is cut off mid-send.
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        for monitor in monitors:
            monitor.cancel()
        await asyncio.gather(*monitors, return_exceptions=True)
        await bot.session.close()
        await loe.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
