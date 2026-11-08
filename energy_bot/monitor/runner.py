import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


async def run_forever(
        name: str, interval_seconds: float, job: Callable[[datetime], Awaitable[None]], tz: ZoneInfo
) -> None:
    """Call `job(now)` every `interval_seconds` until cancelled. A failing run is logged and never stops the loop."""
    while True:
        try:
            await job(datetime.now(tz))
        except Exception as exc:
            logger.error(f"{name} failed: {exc}", exc_info=exc)
        await asyncio.sleep(interval_seconds)
