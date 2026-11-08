# Detailed implementation plan: LOE power-outage Telegram bot

## Context
Outages in Lviv region are getting worse. The bot remembers each subscriber's address, works out their outage group (черга ГПВ), and sends:
- schedule changes for their group (old → new) and newly published schedules for tomorrow;
- warnings 60 and 30 minutes before a scheduled outage, including when power should be back;
- emergency outage start (with the planned restore time) and end.

The repo has only docs committed (`[init] the project`). Hosting: Oracle Cloud Always Free VM; the LOE APIs are reachable from non-UA IPs.

## Decisions (agreed with user)
- Access: an allow-list of Telegram user IDs in `.env` (`ALLOWED_USER_IDS`). Everyone else gets "Цей бот приватний."
- Night: notifications are still sent during quiet hours, but **silently** (`disable_notification=True`). Each user sets their own hours; the default is 23:00–07:00.
- One address per user. `/address` replaces it.
- A schedule change message shows **old → new** periods for that day.
- Bot texts are in Ukrainian; code and docs are in English.
- **The schedule is shown as a rendered PNG** in style "A – Amber night" with left/right half-hour split. Reference: `schedule_image_mockup.png` (next to this file); the exact palette and layout are specified under `energy_bot/render/` below.
  - Sent by `/schedule` (today + tomorrow), schedule-change messages and the "tomorrow published" message.
  - `/status` stays a short text: power now? when it changes next, any active emergency, address, group, quiet hours.

## Verified API facts (drive the design)
- **Schedule:** `GET https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic`. Use the `menuItems` named `Today` and `Tomorrow`; an empty `rawHtml` means no schedule.
  - Real lines (checked against ~3,000 archived ones):
    - `Група X.Y. Електроенергії немає з HH:MM до HH:MM[, з HH:MM до HH:MM]{0,4}.`
    - `Група X.Y. Електроенергія є.`
    - header lines `Графік погодинних відключень на DD.MM.YYYY` and `Інформація станом на HH:MM DD.MM.YYYY`.
  - Times are on 30-min steps. `24:00` is frequent. An outage often runs to 24:00 and continues from 00:00 the next day.
  - Glitch: `з 00:00 до 00:00` appears in some archives; it is ignored as a zero-length placeholder.
- **Address:** `https://power-api.loe.lviv.ua/api` (Hydra JSON).
  - `pw_cities?pagination=false&name=<part>` does a **partial, case-insensitive** search and returns the OTG name too.
  - `pw_streets?pagination=false&city.id=X&name=<part>` is partial as well.
  - `pw_accounts?pagination=false&city.id=X&street.id=Y&buildingName=171` is an exact building match; the group is `chergGpv`. Only `buildingName` and `chergGpv` are ever read.
- **Emergencies:** `pw_accidents?city.id=X&street.id=Y` (first page of 30 is enough for one street).
  - Fields: `id`, `buildingNames` ("5, 9" or empty = whole street), `dateEvent` (start), `datePlanIn` (planned restore), `typeOff`, `koment`.

## Project structure
```
.env.example                      BOT_TOKEN, ALLOWED_USER_IDS + optional overrides
pyproject.toml / uv.lock          deps + [tool.pytest.ini_options] testpaths, asyncio_mode=auto
energy_bot/
  __init__.py                     (empty — every package has an empty __init__.py)
  main.py                         entry point
  config.py                       Settings
  loe/        client.py, schemas.py, parser.py, buildings.py (building number normalisation)
  schedule/   timeline.py, schemas.py       pure time logic (no IO)
  render/     schedule_image.py, theme.py, fonts/ (Inter Regular+Bold .ttf + OFL.txt)
  storage/    db.py, schemas.py
  bot/        handlers.py, states.py, keyboards.py, middlewares.py, texts.py
  monitor/    schedule_watcher.py, warnings.py, accident_watcher.py, notifier.py
tests/
  fixtures/   schedule_*.html (real archived rawHtml), accidents.json, streets.json
  test_parser.py, test_timeline.py, test_db.py, test_client.py,
  test_schedule_watcher.py, test_warnings.py, test_accident_watcher.py
deploy/       energy-bot.service, README.md, AGENTS.md
```

## Module specs

### `energy_bot/config.py`
`Settings(BaseSettings)` reads `.env`:
- `bot_token: SecretStr`
- `allowed_user_ids: list[int]`
- `db_path="energy_bot.db"`
- `timezone="Europe/Kyiv"`
- `schedule_poll_seconds=300`, `accident_poll_seconds=180`, `warning_tick_seconds=60`
- `warning_offsets_minutes=[60, 30]`, `warning_catchup_minutes=10`
- `default_quiet_start="23:00"`, `default_quiet_end="07:00"`
- `log_level="INFO"`
- property `tz -> ZoneInfo`

### `energy_bot/loe/schemas.py`
- `Interval(start_minutes: int, end_minutes: int)` in minutes since midnight. `end_minutes` is 1–1440, so that 24:00 is representable.
- `DaySchedule(date: date, info_as_of: datetime | None, groups: dict[str, list[Interval]])`
- `MenuItem(name, raw_html)`
- `City(id, name, otg_id, otg_name)`
- `Street(id, name)`
- `Accident(id, city_id, street_id, building_names: list[str], date_event: datetime, date_plan_in: datetime | None, type_off: int | None, comment: str)`

### `energy_bot/loe/parser.py`
`parse_schedule_html(raw: str) -> DaySchedule | None`
1. Strip tags.
2. Read the date with `на (\d\d\.\d\d\.\d{4})` and the as-of time with `станом на (\d\d:\d\d \d\d\.\d\d\.\d{4})`.
3. For each `Група (\d\.\d)\.(.*)`, use `findall(r"з (\d\d:\d\d) до (\d\d:\d\d)")`.
4. Drop zero-length intervals. Treat `24:00` as end 1440.
5. Return `None` if there is no date or no groups.

### `energy_bot/loe/client.py`: `LoeClient`
Wraps one shared `httpx.AsyncClient` with a generic UA and a 30 s timeout. Network errors, 429 and 5xx get one retry after 2 s. It raises `LoeError` on failure; malformed records are skipped one by one.

Methods:
- `get_schedules() -> list[DaySchedule]`: Today and Tomorrow, parsed; `None`s are skipped.
- `search_cities(text) -> list[City]`
- `search_streets(city_id, text) -> list[Street]`
- `find_groups(city_id, street_id, building) -> BuildingLookup(found, groups, building)`: `building` is LOE's spelling of the matched building, and it's what gets stored. tries the canonical spelling (`116а` → `116-А`) first, then as typed and in upper and lower case. `found=True` with empty `groups` means the building isn't on the hourly schedule ("Не входить").
- `get_accidents(city_id, street_id) -> list[Accident]`: first page only.

### `energy_bot/schedule/timeline.py` (pure functions; most of the logic and the most tests)
- `to_blocks(schedules: list[DaySchedule], group, tz) -> list[OutageBlock]`: converts each day's intervals for the group into aware datetimes, then **merges touching or overlapping intervals across days**. For example, 22:00–24:00 today plus 00:00–02:00 tomorrow becomes one block ending at 02:00 tomorrow. `OutageBlock(start: datetime, end: datetime)`
- `due_warnings(blocks, now, offsets, catchup) -> list[(OutageBlock, offset)]`: a warning is due when `start - offset <= now < start - offset + catchup` and `now < start`.
- `current_block(blocks, now)` and `next_block(blocks, now)`, used by `/status` and `/schedule`.
- `change_to_announce(old: DaySchedule, new: DaySchedule, group) -> GroupChange | None`: `None` if there is nothing to tell the user (same periods, or the group is absent from `new`).
- `is_quiet(now, quiet_start, quiet_end) -> bool`: handles ranges that wrap midnight.

### `energy_bot/render/` (Pillow; pure, no IO except reading the fonts)
- `theme.py`: colour constants of the chosen palette:
  - bg `#121418`, title `#F4F4F6`, sub `#8A93A3`
  - power on `#F2B544` (text `#3A2A06`), power off `#262B35` (text `#7D8696`)
  - current-hour ring `#5CE1E6`, progress track `#3A4150`, chips `#232833`/`#F2B544`
  - tile radius 18
- `fonts/`: Inter Regular + Bold (SIL OFL, bundled with its licence, so rendering is identical on Windows and the Ubuntu VM).
- `schedule_image.py`: `render_day(day: DaySchedule, group: str, now: datetime) -> bytes` (PNG, 1080 px wide). `now` is always the current local time: it decides the "Сьогодні/Завтра" title, and whether a ring is drawn (only when it falls on `day`).
  - Header: "Сьогодні · пт 07.11" / "Завтра · сб 08.11" / plain date for other days, and "Група 5.1 · станом на 14:05".
  - Grid: 4 columns × 6 rows of hour tiles labelled "00:00"…"23:00". Each tile is split left (:00–:30) / right (:30–:00), and each half is painted on or off. The hour label changes color at the split, so it's readable over both halves.
  - Current hour (only when `now` falls on that date): a ring around the tile, plus a progress bar inside it for minutes elapsed.
  - Footer:
    - chips "Без світла 8,5 год" and "N вимкнення/вимкнень" (Ukrainian plural helper);
    - the period list, wrapping onto extra lines when long;
    - a legend ("є світло", "немає світла", "зараз HH:MM" only when the ring is drawn).
  - A day with no outages: all tiles on, and a chip "Відключень не заплановано".
  - Drawn at 2× and downscaled with LANCZOS for anti-aliasing. Callers run it via `asyncio.to_thread` so the event loop isn't blocked.

### `energy_bot/storage/db.py`: `Database` (aiosqlite, one connection, WAL mode)
```sql
subscribers(chat_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, outage_group TEXT NOT NULL,
  city_id INTEGER, city_name TEXT, otg_name TEXT, street_id INTEGER, street_name TEXT, building TEXT,
  quiet_start TEXT NOT NULL, quiet_end TEXT NOT NULL, quiet_enabled INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1)
schedule_snapshots(date TEXT PRIMARY KEY, schedule_json TEXT NOT NULL)   -- whole DaySchedule as JSON
sent_notifications(chat_id INTEGER, key TEXT, sent_at TEXT, PRIMARY KEY(chat_id, key))
active_accidents(chat_id INTEGER, accident_id INTEGER, date_plan_in TEXT, PRIMARY KEY(chat_id, accident_id))
```
- Subscribers: `upsert_subscriber` (also used by `/group`: the address fields are cleared, so there's no emergency tracking), `get_subscriber`, `active_subscribers`, `set_quiet_hours`, `deactivate`, `delete_subscriber`.
- Snapshots: `has_snapshots()`, `get_snapshot(date)`, `recent_snapshots(since)`, `save_snapshot(DaySchedule)`.
- Notifications: `is_sent(chat_id, key)` and `mark_sent(chat_id, key, now)`. The sender marks only **after** a successful send, so a failed send is retried on the next tick.
- Accidents: `active_accidents(chat_id)`, `save_accident(chat_id, ActiveAccident)` (insert or update the restore time), `remove_accident`.
- `prune(now)`: drops snapshots older than 7 days and sent keys older than 3 days.
- `storage/schemas.py` holds the `Subscriber` (with `has_address`) and `ActiveAccident` pydantic models.

### `energy_bot/bot/`
- `middlewares.py`: `AllowListMiddleware`, an outer middleware on messages and callbacks. A non-allowed user gets the refusal text, and the handler doesn't run.
- `states.py`: `AddressForm`: `city → street → building → group_choice`.
- `keyboards.py`: up to 8 inline buttons per choice list, plus "Скасувати".
- `texts.py`: all Ukrainian message templates and the time formatting.
- `handlers.py`:

| Command | Behaviour |
|---|---|
| `/start` | greeting + command list; new users → prompts `/address` |
| `/address` | FSM: "Введіть населений пункт" → `search_cities` → buttons "Львів (Львівська ОТГ)" → "Введіть вулицю" → `search_streets` → buttons → "Введіть номер будинку" → `find_groups`: 1 group → save; several → buttons; none → "Будинок не знайдено, перевірте номер або встановіть групу вручну: /group 5.1". Confirms with today's schedule for the group. |
| `/group 5.1` | validate `^[1-6]\.[12]$`, save without address (warns that emergency alerts need an address) |
| `/schedule` | photo of today (current hour ringed) + photo of tomorrow if published, without caption (the image already shows totals and periods). Source: `bot/schedule_source.load_schedules` (stored snapshots, or LOE if today's isn't stored; never saved). If nothing is published: "Графік для вашої групи ще не опубліковано" |
| `/status` | text only: "🔴 Зараз світла немає. З'явиться о 15:30" / "🟢 Світло є. Наступне вимкнення о 20:00 (до 22:00)", active emergencies with restore time, address, group, quiet hours |
| `/quiet 23:00 07:00` / `/quiet off` | set/disable quiet hours |
| `/stop` | delete subscriber data |
| `/cancel` | leave FSM |

### `energy_bot/monitor/`
- `notifier.py`: `Notifier.send(sub, text)` and `Notifier.send_photo(sub, png: bytes, caption)` (via `BufferedInputFile`). Both use `disable_notification=is_quiet(...)`. When one event goes to many subscribers, the image is rendered once per `(date, group)`. It retries on `TelegramRetryAfter`, deactivates the subscriber on `TelegramForbiddenError`, logs other errors, and waits 50 ms between sends.

- **`schedule_watcher.py`** runs every 5 min:
  1. `get_schedules()`. On error, log and skip the cycle.
  2. For each `DaySchedule`, compare it with the `get_snapshot(date)` stored for that date.
     - No previous snapshot and this isn't the first run (the DB has some snapshot) → **photo** of that day for the group, captioned "📅 Опубліковано графік на {date}".
     - Previous snapshot exists → for each subscriber, `change_to_announce`. If changed, send a **photo** of the new schedule (ringed if it's today), captioned "🔄 Графік на {date} змінено\nБуло: 17:00–20:00\nСтало: 18:00–21:00".
     - Then `save_snapshot`.
  3. On the first run (empty DB), save silently.
  4. If `Today` becomes empty, nothing happens: the last snapshot is kept.

- **`warnings.py`** runs every 60 s:
  1. For each subscriber, build `to_blocks(recent snapshots for yesterday/today/tomorrow, outage_group)`.
  2. For each due `(block, offset)` not yet `is_sent(chat, f"warn|{block.start.isoformat()}|{offset}")`, send "⏰ Через {offset} хв (о {start}) вимкнення світла. Світло має з'явитися о {end}{' завтра' if next day}." If the block ends at `known_until` (next day unpublished): "…не раніше 00:00 (графік на завтра ще не опубліковано)."
  3. Because the key includes the block start, a schedule change that moves an outage produces fresh warnings.

- **`accident_watcher.py`** runs every 3 min:
  1. Group active subscribers that have an address by `(city_id, street_id)` and call `get_accidents` once per group. On error, skip that group.
  2. Building match: normalise (lowercase, remove spaces) and test `building in building_names`; an empty list means the whole street.
  3. Compare the matches with `active_accidents(chat)`:
     - New → "⚠️ Аварійне відключення з {dateEvent:%H:%M}. Орієнтовне відновлення: {datePlanIn}." and `save_accident`.
     - Changed `datePlanIn` → "🕑 Оновлено час відновлення: {new}" and `save_accident`.
     - Gone → "✅ Аварійне відключення завершено." and `remove_accident`.

### `energy_bot/main.py`
1. Set up logging and load Settings.
2. `Database.connect()` + migrate, and create `LoeClient`.
3. Create `Bot` and `Dispatcher` with `MemoryStorage` for FSM. Register the middleware and the router, and inject `db`, `loe` and `settings` through `dp` workflow data.
4. On startup, create the three monitor tasks with `asyncio.create_task` (each loop catches and logs every exception, so a crashing loop never kills the bot), plus a daily `prune`.
5. On shutdown, cancel the tasks and close the HTTP client and the DB.
6. `dp.start_polling(bot)`.

## Steps and commit points
After every step I stop, show the changes and the proposed message, and commit **only after your approval**. Never push. Each step includes its DOX pass, updating the affected `AGENTS.md`, the `CLAUDE.md` facts and the `README.md`.

| # | Content | Proposed message |
|---|---|---|
| 1 | deps (`uv add`), `uv.lock`, pytest config, `config.py`, `.env.example`, empty `__init__.py` files | `[add] dependencies and config` |
| 2 | `loe/` schemas + parser + client, tests with real fixtures and respx | `[add] LOE API client and schedule parser` |
| 3 | `schedule/timeline.py` + tests (cross-midnight merge, warnings window, diff, quiet hours) | `[add] outage timeline logic` |
| 4 | `render/` (Pillow dep, Inter fonts, theme, `render_day`) + tests | `[add] schedule image rendering` |
| 5 | `storage/` + tests (tmp-file SQLite) | `[add] SQLite storage` |
| 6 | `bot/` + `main.py` (polling, commands, address FSM, allow-list); README commands updated (`/quiet`) | `[add] bot commands and address setup` |
| 7 | `monitor/` + wiring in `main.py` + tests | `[add] outage monitors and notifications` |
| 8 | `deploy/energy-bot.service`, `deploy/README.md` (Oracle VM: create instance, install uv, clone, `.env`, `systemctl enable --now`, logs), `deploy/AGENTS.md` | `[add] deployment guide` |

## Verification
- `uv run pytest` after each step. Key cases:
  - parser on real archived HTML (1–5 intervals, "Електроенергія є", 24:00, the 00:00–00:00 glitch);
  - a block crossing midnight, with the warning's return time on the next day;
  - warning dedupe across ticks and across restarts;
  - schedule diff → only affected groups notified;
  - accident start / plan-update / end;
  - quiet hours wrapping midnight;
  - renderer:
    - valid PNG, 1080 px wide;
    - sampled pixel colors for a fully-off tile, the left/right halves of a half-hour tile, and the ring present only when `now` is that day;
    - "no outages" variant;
    - plural forms (1 вимкнення, 3 вимкнення, 5 вимкнень).
  - Sample PNGs are written to a temp dir during tests for manual viewing.
- Manual run after step 6: `uv run python -m energy_bot.main` with a real token. Run `/address` for Львів → Городоцька → 171 and expect group 5.1. Compare `/schedule` with poweron.loe.lviv.ua. Check that a non-allowed account gets the refusal.
- Manual check after step 7: set `WARNING_OFFSETS_MINUTES` so a warning is due for a real upcoming outage (or seed a test snapshot), and confirm exactly one message per offset with the correct return time. Check silent delivery inside the quiet hours.
- Deployment: follow `deploy/README.md` on the VM and watch `journalctl -u energy-bot -f` over several poll cycles.
