# energy_bot/loe

## Purpose

- The only gateway to Lvivoblenergo (LOE) data. Wraps the unofficial JSON APIs behind poweron.loe.lviv.ua.

## Ownership

- `client.py`: `LoeClient` (async httpx). Schedule items, OTG/city/street lists, building → group lookup, emergency outages (paginated).
- `schemas.py`: pydantic DTOs: `Otg`, `City`, `Street`, `Account`, `Accident`, `MenuItem`, `Interval`, `DaySchedule`.
- `parser.py`: `parse_schedule_html(raw) -> DaySchedule | None`.

## Local Contracts

- Schedule: `GET https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic`. Use the `menuItems` named `Today` and `Tomorrow`; an empty `rawHtml` means no schedule.
- `rawHtml` lines: `Група X.Y. Електроенергії немає з HH:MM до HH:MM[, з HH:MM до HH:MM].` or `Група X.Y. Електроенергія є.` The parser extracts every `з … до …` pair; `24:00` means end of day. The date comes from `Графік погодинних відключень на DD.MM.YYYY`.
- Address: `https://power-api.loe.lviv.ua/api/` `pw_otgs` → `pw_cities?otg.id=` → `pw_streets?city.id=` → `pw_accounts?city.id=&street.id=&buildingName=`, always with `pagination=false`. The group is the `chergGpv` field. A building may return several groups.
- Personal data: `pw_accounts` records may contain personal fields. Schemas model only `buildingName` and `chergGpv`, and these records are never logged or stored.
- Emergencies: `pw_accidents?page=N&otg.id=&city.id=&street.id=`. Follow `hydra:view` paging. `buildingNames` is a comma-separated list; `dateEvent` is the start and `datePlanIn` the planned restore.
- HTTP: generic User-Agent, 30 s timeout, retries with backoff. Errors raise; callers decide whether to skip.

## Work Guidance

- If an endpoint shape changes, update the schemas, this file and the LOE facts in `CLAUDE.md` together.

## Verification

## Child DOX Index

- None
