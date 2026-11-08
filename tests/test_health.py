import socket

import httpx

from energy_bot.health import start_health_server


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def test_health_endpoint_answers_ok_and_stops():
    port = free_port()
    runner = await start_health_server("127.0.0.1", port)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{port}/")
        assert (response.status_code, response.text) == (200, "ok")
    finally:
        await runner.cleanup()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))  # the port is free again after cleanup
