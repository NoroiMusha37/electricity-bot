import asyncio
from unittest.mock import AsyncMock

import pytest

from energy_bot.monitor.runner import run_forever
from tests.conftest import KYIV


async def test_failing_run_is_logged_and_loop_continues(caplog):
    job = AsyncMock(side_effect=[RuntimeError("boom"), None, asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await run_forever("test job", 0, job, KYIV)
    assert job.await_count == 3
    assert "test job failed: boom" in caplog.text
