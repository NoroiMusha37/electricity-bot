# energy_bot/loe

## Purpose

- The only gateway to Lvivoblenergo (LOE) data. Wraps the unofficial JSON APIs behind poweron.loe.lviv.ua.

## Ownership

- `client.py`: `LoeClient` (async httpx), `LoeError`.
  - `get_schedules()`: Today/Tomorrow parsed.
  - `search_cities(text)`, `search_streets(city_id, text)`: ranked exact → prefix → substring.
  - `find_groups(city_id, street_id, building) -> BuildingLookup`.
  - `get_accidents(city_id, street_id)`: first page only.
- `schemas.py`: pydantic DTOs.
  - Our own: `Interval`, `DaySchedule`, `BuildingLookup`, plus the shared formatting helpers `format_minutes` and `WEEKDAYS` (used by both the bot texts and the renderer).
  - Read straight from LOE JSON records via field aliases and validators: `MenuItem`, `City`, `Street`, `BuildingAccount`, `Accident`.
- `parser.py`: `parse_schedule_html(raw, tz) -> DaySchedule | None`.
- `buildings.py`: building number normalisation (`normalize_building`, `building_variants`, `parse_building_names`, `building_matches`).

## Local Contracts

- Schedule: `GET https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic&jsonld=1`. `jsonld=1` is required: without it this server returns a plain JSON list, not a Hydra collection. LOE's own frontend sends it too. Use the `menuItems` named `Today` and `Tomorrow`; an empty `rawHtml` means no schedule, and the day is omitted.
- `rawHtml` lines: `Група X.Y. Електроенергії немає з HH:MM до HH:MM[, з HH:MM до HH:MM].` or `Група X.Y. Електроенергія є.` (→ empty list).
  - The parser extracts every `з … до …` pair.
  - `24:00` (and an end of `00:00`) means end of day.
  - Zero-length `з 00:00 до 00:00` placeholders are dropped.
  - The date comes from `Графік погодинних відключень на DD.MM.YYYY`.
- `Interval` stores minutes since midnight: `start_minutes` is 0–1439, `end_minutes` is 1–1440 and exclusive. `Interval.label` formats it as `HH:MM–HH:MM`.
- Address: `https://power-api.loe.lviv.ua/api/` `pw_cities?name=` (partial, case-insensitive) → `pw_streets?city.id=&name=` → `pw_accounts?city.id=&street.id=&buildingName=` (exact match), always with `pagination=false`.
  - The group is `chergGpv` and must match `^\d\.\d$`. `"Не входить"` means the building isn't on the hourly schedule: `BuildingLookup(found=True, groups=set())`.
  - A building may return several groups.
  - `BuildingLookup.building` is LOE's spelling of the matched building (`buildingName` of the first record). Store this, not the raw user input.
- Building numbers: LOE spells them `116`, `116-А` (uppercase Cyrillic letter after a dash), `111/1`, `11-13`. Always compare through `normalize_building()`, which handles `116а`, `116 А` and a Latin `116A`.
- Personal data: `pw_accounts` records are read only for `buildingName` and `chergGpv`. Never log or store them.
- Emergencies: `pw_accidents?city.id=&street.id=`. Only the first page (30 records) is read; a single street never has that many at once.
  - `buildingNames` is a comma-separated list.
  - **Unverified assumption:** an empty `buildingNames` means the whole street. No real record with an empty list had been seen as of 2026-11-07, but it's the safe choice (over-warn rather than miss). Revisit if LOE data shows otherwise.
  - `dateEvent` is the start and `datePlanIn` the planned restore. Naive datetimes get the tz passed as validation `context={"tz": ...}` (`LoeClient` does this).
- HTTP: generic User-Agent, 30 s timeout, **one** retry after `RETRY_DELAY_SECONDS` (2 s) on network errors, 429 and 5xx. More isn't needed: warnings are sent from stored schedules, and the next poll retries anyway. Other 4xx responses, bad JSON and a non-object JSON body raise `LoeError` immediately; callers decide whether to skip.
- Hydra: all list responses are Hydra collections (JSON-LD from API Platform): items in `hydra:member`, related objects as IRIs (`/api/pw_otgs/28`), accepted filters in `hydra:search`.
- Malformed records: each record is validated separately (`_validate_records`). A bad one (missing field, bad date, not an object) is skipped with a warning and never hides the others. The warning lists only field names and reasons, never record contents (personal data).
- Unexpected response structure (missing `hydra:member`, menu or `menuItems`) raises `LoeError`.

## Work Guidance

- If an endpoint shape changes, update the schemas, this file and the LOE facts in `CLAUDE.md` together.

## Verification

- `uv run pytest tests/test_parser.py tests/test_buildings.py tests/test_client.py`

## Child DOX Index

- None
