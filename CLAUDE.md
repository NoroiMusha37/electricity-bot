# CLAUDE.md

This file provides guidance to agents when working with code in this repository.

## Facts
Every time you get new information about this project, or new way of interaction with 
library/models/services, or specific instructions from user on how to test/implement new feature,
add short description of acquired knowledge here in bulleted list:
- After work is done in worktrees - merge worktree branch into main locally (`git merge`); do NOT push worktree branches to remote; Delete worktree after successful merge;
- If needed DTO model - create pydantic schema in separate schemas.py file related to working module
- Never add anything to `__init__.py`. Use full-path imports.
- Naming: use descriptive names (`record`, not `m`); prefer a private method over a nested function. This applies to tests too.
- Efficiency: don't create variables that can be omitted. Avoid extra copies: prefer `list.sort()` to `sorted()` on a fresh list, use generators to filter, don't call `.strip()` twice on the same string (use walrus), and filter out unneeded items before validating them.
- Comments: no section-divider or banner comments (`# ------ ...`) and no comments that narrate what the code does. Use a short docstring or inline comment only for a non-obvious reason.
- Logging: always use f-strings (`logger.warning(f"... {url} ...")`); never pass values as `%s` arguments.
- `Settings` fields in `energy_bot/config.py` are UPPERCASE (`BOT_TOKEN`, `ALLOWED_USER_IDS`, ...), including the `TZ` property.
- Git: never push. Commit messages are one line `[verb] the rest` (e.g. `[init] the project`): no body, no co-author/tool attribution. Never commit on your own: stop at each milestone, present the changes and the proposed message, and commit only after the user approves both.
- Project: Telegram bot (aiogram 3, long polling) notifying about Lvivoblenergo (LOE) outages. Package manager is `uv`; timezone for all schedule logic is `Europe/Kyiv`. Target hosting is an Oracle Cloud Always Free VM. The LOE APIs are reachable from non-UA IPs (verified 2026-11-06 via a US-hosted fetch), so there's no geo-block.
- Step workflow: after a step's code is written and tested, explain it file by file in detail, stopping after each file for questions. Then propose improvements and simplifications, apply the agreed ones, and only then propose the commit.
- Do research and feasibility checks (API access, geo-blocking, etc.) during planning, before implementation. Don't put developer to-dos or pre-checks in README: README describes the project for its users.
- LOE schedule API: `GET https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic` → `hydra:member[0].menuItems`, items named `Today`/`Tomorrow` hold `rawHtml` (empty = no schedule). Lines look like `Група 2.1. Електроенергії немає з 17:00 до 20:00.` or `Група 6.2. Електроенергія є.`; groups 1.1–6.2. Header lines: `Графік погодинних відключень на DD.MM.YYYY` and `Інформація станом на HH:MM DD.MM.YYYY`.
- LOE address API (`https://power-api.loe.lviv.ua/api`, Hydra JSON, add `pagination=false`): `pw_otgs` → `pw_cities?otg.id=` (Lviv city id 693, OTG 28) → `pw_streets?city.id=` → `pw_accounts?city.id=&street.id=&buildingName=` (exact building match). The group is `chergGpv` (e.g. `"5.1"`); `"Не входить"` means the building isn't on the hourly schedule. Never store or log `pw_accounts` personal fields. `pw_cities` and `pw_streets` also accept `name=` (partial, case-insensitive).
- LOE building numbers look like `116`, `116-А` (uppercase Cyrillic letter after a dash), `111/1`, `11-13`, the same in `pw_accounts` and `pw_accidents.buildingNames`. Always compare via `energy_bot.loe.buildings.normalize_building`.
- LOE emergency API: `pw_accidents?city.id=&street.id=` (paginated by 30, but only page 1 is read: one street never has that many). Fields: `id`, `buildingNames` (comma list like `"5, 9"`), `dateEvent` (start), `datePlanIn` (planned restore), `typeOff`, `koment`.
- Windows console: when inspecting API JSON from bash, decode bytes explicitly (`json.loads(sys.stdin.buffer.read())`) and print with ASCII escapes; Cyrillic otherwise prints garbled.

