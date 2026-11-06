# energy-bot

Telegram bot for Lviv region power outages, using public data from Львівобленерго
([poweron.loe.lviv.ua](https://poweron.loe.lviv.ua)).

## Features

- Remembers your address and works out your outage group (черга ГПВ, e.g. `5.1`) from it.
- Notifies when your group's hourly outage schedule (ГПВ) changes or tomorrow's schedule is published.
- Warns **60 and 30 minutes** before a scheduled outage, including when power should be back.
- Notifies when an **emergency outage** (аварійне відключення) at your address starts, with the planned restore time,
  and when it ends.
- Supports several subscribers (family, neighbours), each with their own address.

## Bot commands

| Command      | Action                                                      |
|--------------|-------------------------------------------------------------|
| `/start`     | Greeting and help                                           |
| `/address`   | Set or change your address (settlement → street → building) |
| `/group 5.1` | Set the group manually if the address lookup fails          |
| `/schedule`  | Today's and tomorrow's schedule for your group              |
| `/status`    | Your saved address, group and any active emergency outage   |
| `/stop`      | Unsubscribe and delete your data                            |

## Data sources

These are unofficial: they're the JSON APIs behind the LOE website, and they may change without notice.

| Purpose                            | Endpoint                                                                                 |
|------------------------------------|------------------------------------------------------------------------------------------|
| Hourly schedule (today / tomorrow) | `https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic`                             |
| Address → group                    | `https://power-api.loe.lviv.ua/api/pw_otgs` → `pw_cities` → `pw_streets` → `pw_accounts` |
| Emergency outages                  | `https://power-api.loe.lviv.ua/api/pw_accidents`                                         |

## Tech stack

Python 3.13, [uv](https://docs.astral.sh/uv/), aiogram 3 (long polling, so no public URL is needed), httpx, pydantic,
aiosqlite (SQLite).

## Local run

```bash
uv sync
cp .env.example .env        # set BOT_TOKEN (from @BotFather) and ALLOWED_USER_IDS
uv run python -m energy_bot.main
uv run pytest               # tests
```

## Deployment

The bot runs as a systemd service on any Linux host, e.g. an Oracle Cloud Always Free VM. See `deploy/README.md`.
