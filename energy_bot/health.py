"""Minimal HTTP endpoint answering "ok".

Hosts that run programs as websites (alwaysdata "User program") need the process to listen on a port, and an
external pinger hitting it keeps the program running. The bot itself doesn't need it.
"""

from aiohttp import web


async def _ok(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def start_health_server(host: str, port: int) -> web.AppRunner:
    """Serve GET / on host:port; call `cleanup()` on the returned runner to stop it."""
    app = web.Application()
    app.router.add_get("/", _ok)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
