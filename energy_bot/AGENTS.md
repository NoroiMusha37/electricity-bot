# energy_bot

## Purpose

- Application package: the Telegram bot and its background monitors.

## Ownership

- `main.py`: entry point (`python -m energy_bot.main`). Builds the Bot and Dispatcher, initialises the DB, starts the monitor tasks, runs long polling.
- `config.py`: `Settings` (pydantic-settings, read from `.env`): `BOT_TOKEN`, `DB_PATH`, poll intervals, timezone.
- `bot/`: Telegram layer: command handlers, the address-entry FSM (`states.py`), inline keyboards.
- `storage/`: SQLite persistence (`db.py`) and its DTOs (`schemas.py`).
- `monitor/`: background asyncio loops: `schedule_watcher.py` (schedule diffs), `warnings.py` (60/30-min warnings), `accident_watcher.py` (emergency start/end), `notifier.py` (safe message sending).
- Child-owned: `loe/` (see its AGENTS.md).

## Local Contracts

- All time logic uses `ZoneInfo("Europe/Kyiv")`; never naive datetimes.
- Monitors never notify on a failed fetch. They keep the last good data and log the error.
- Every notification is deduplicated through the DB (`sent_notifications`, `active_accidents`), so a restart never causes duplicate messages.
- Warnings merge back-to-back outage intervals and always state when power should return.
- A subscriber who blocks the bot is deactivated, not deleted.
- Bot handlers do no HTTP calls of their own; they go through `energy_bot.loe.client.LoeClient`.

## Work Guidance

- Keep `__init__.py` empty; use full-path imports.
- New DTOs go in the `schemas.py` of the owning subpackage.

## Verification

## Child DOX Index

- `loe/AGENTS.md`: Lvivoblenergo API client, response schemas and schedule HTML parser
