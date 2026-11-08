# energy_bot

## Purpose

- Application package: the Telegram bot and its background monitors.

## Ownership

- `main.py`: entry point (`python -m energy_bot.main`). Builds the Bot and Dispatcher, initialises the DB, starts the monitor tasks, runs long polling.
- `health.py`: `start_health_server(host, port)`, a tiny aiohttp endpoint answering "ok". Started by `main.py` only when `HEALTH_PORT` is set; used by hosts that run programs as websites, plus an external pinger.
- `config.py`: `Settings` and the module-level `settings = Settings()` used everywhere (pydantic-settings, read from `.env`; template in `/.env.example`): `BOT_TOKEN`, `ALLOWED_USER_IDS`, `DB_PATH`, timezone, poll intervals, warning offsets and catch-up window, default quiet hours, log level. List settings accept `1,2` or `[1, 2]`.
- `schedule/`: pure outage-timeline logic, no IO.
  - `timeline.py`: `to_blocks` (merge across midnight), `known_until` (where schedule knowledge ends), `due_warnings`, `current_block`, `next_block`, `change_to_announce`, `is_quiet`.
  - `schemas.py`: `OutageBlock`, `DueWarning`, `GroupChange`.
- `render/`: schedule PNG rendering (Pillow), look defined by `docs/schedule_image_mockup.png`.
  - `schedule_image.py`: `render_day(day, group, now) -> bytes`, `tile_box(hour)`, `outages_word(count)`, `format_hours(minutes)`.
    - Layout constants are in canvas pixels (final × `SCALE`); `tile_box` converts back to final pixels.
    - `render_day` raises `ValueError` if the group isn't in the day: never draw an unknown schedule as "no outages".
  - `theme.py`: colour constants.
  - `fonts/`: Inter Regular/Bold + `OFL.txt` licence (keep the licence next to the fonts).
  - `render_day` is CPU-bound (~0.1 s); call it via `asyncio.to_thread` from async code.
- `bot/`: Telegram layer.
  - `handlers.py`: one `router` with all commands, the address dialogue (FSM) and the error handler. `db` and `loe` are injected by aiogram from `Dispatcher(db=..., loe=...)`.
  - `states.py` (`AddressForm`), `schemas.py` (callback data), `keyboards.py` (`choices_keyboard`), `middlewares.py` (`AllowListMiddleware`).
  - `texts.py`: every Ukrainian text and its formatting (`status`, `moment`, ...). Keep texts out of the handlers.
  - `schedule_source.py`: `load_schedules` = stored snapshots, or LOE when today's isn't stored. It never saves: the schedule watcher is the only snapshot writer.
- `storage/`: SQLite persistence.
  - `db.py`: `Database.connect(path)`; one aiosqlite connection, WAL; tables created with `CREATE TABLE IF NOT EXISTS`.
  - `schemas.py`: `Subscriber` (field `outage_group`; `has_address`), `ActiveAccident`.
  - Schedules are stored as whole `DaySchedule` JSON per date; times and datetimes as ISO strings.
- `monitor/`: background jobs, each a plain `async def job(..., now)` started by `runner.run_forever` from `main.py` (`functools.partial` binds the dependencies).
  - `schedule_watcher.check_schedules`: the **only** writer of schedule snapshots. The first run on an empty DB is silent; after that it sends "published"/"changed" photos, rendered once per group. Past days are stored but not announced. Known, accepted limitation: if a send fails, the snapshot is saved anyway, so that one "published"/"changed" notice isn't retried (warnings still use the new schedule). The fix would be per-user `sent_notifications` keys; do it only if it shows up in the logs.
  - `outage_warnings.send_due_warnings`: 60/30-min warnings from stored snapshots; dedupe key `warn|<block start ISO>|<offset>`, marked only after delivery.
  - `accident_watcher.check_accidents`: one LOE request per street; start / restore-time change / end; DB state changes only after delivery. Saving a new address or group clears the chat's `active_accidents` (`db.clear_accidents`), so an old address never produces a false "ended".
  - `notifier.Notifier`: `send_text` / `send_photo` return delivery success. Silent during quiet hours, one wait on rate limit, deactivates chats that blocked the bot, never raises Telegram errors.
  - `runner.run_forever(name, interval, job, tz)`: calls `job(datetime.now(tz))` forever; a failing run is logged, not fatal.
- Child-owned: `loe/` (see its AGENTS.md).

## Local Contracts

- All time logic uses `ZoneInfo("Europe/Kyiv")`; never naive datetimes.
- Monitors never notify on a failed fetch. They keep the last good data and log the error.
- Every notification is deduplicated through the DB (`sent_notifications`, `active_accidents`), so a restart never causes duplicate messages.
- Warnings merge back-to-back outage intervals and always state when power should return. If a block ends exactly at `known_until` (next day not published), the return time is hedged: "не раніше 00:00 (графік на завтра ще не опубліковано)". `/status` does the same, and says "Графік на сьогодні ще не опубліковано" rather than "no outages" when today's schedule is unknown.
- A subscriber who blocks the bot is deactivated, not deleted.
- Bot handlers do no HTTP calls of their own; they go through `energy_bot.loe.client.LoeClient`.
- Every button tap must be answered: `stale_button` (registered last) catches taps no other handler accepts, and choice handlers route unknown ids to it.
- Slow handler work (LOE requests, rendering) runs inside `ChatActionSender` so the user sees "typing…" / "sending photo…".

## Work Guidance

- Keep `__init__.py` empty; use full-path imports.
- New DTOs go in the `schemas.py` of the owning subpackage.

## Verification

## Child DOX Index

- `loe/AGENTS.md`: Lvivoblenergo API client, response schemas and schedule HTML parser
