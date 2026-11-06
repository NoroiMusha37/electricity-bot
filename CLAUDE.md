# CLAUDE.md

This file provides guidance to agents when working with code in this repository.

## Facts
Every time you get new information about this project, or new way of interaction with 
library/models/services, or specific instructions from user on how to test/implement new feature,
add short description of acquired knowledge here in bulleted list:
- After work is done in worktrees - merge worktree branch into main locally (`git merge`); do NOT push worktree branches to remote; Delete worktree after successful merge;
- If needed DTO model - create pydantic schema in separate schemas.py file related to working module
- Never add anything to `__init__.py`. Use full-path imports.
- `Settings` fields in `energy_bot/config.py` are UPPERCASE (`BOT_TOKEN`, `ALLOWED_USER_IDS`, ...), including the `TZ` property.
- Git: never push. Commit messages are one line `[verb] the rest` (e.g. `[init] the project`): no body, no co-author/tool attribution. Never commit on your own: stop at each milestone, present the changes and the proposed message, and commit only after the user approves both.
- Project: Telegram bot (aiogram 3, long polling) notifying about Lvivoblenergo (LOE) outages. Package manager is `uv`; timezone for all schedule logic is `Europe/Kyiv`. Target hosting is an Oracle Cloud Always Free VM. The LOE APIs are reachable from non-UA IPs (verified 2026-11-06 via a US-hosted fetch), so there's no geo-block.
- Do research and feasibility checks (API access, geo-blocking, etc.) during planning, before implementation. Don't put developer to-dos or pre-checks in README: README describes the project for its users.
- LOE schedule API: `GET https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic` → `hydra:member[0].menuItems`, items named `Today`/`Tomorrow` hold `rawHtml` (empty = no schedule). Lines look like `Група 2.1. Електроенергії немає з 17:00 до 20:00.` or `Група 6.2. Електроенергія є.`; groups 1.1–6.2. Header lines: `Графік погодинних відключень на DD.MM.YYYY` and `Інформація станом на HH:MM DD.MM.YYYY`.
- LOE address API (`https://power-api.loe.lviv.ua/api`, Hydra JSON, add `pagination=false`): `pw_otgs` → `pw_cities?otg.id=` (Lviv city id 693, OTG 28) → `pw_streets?city.id=` → `pw_accounts?city.id=&street.id=&buildingName=` (exact building match). The group is `chergGpv` (e.g. `"5.1"`). Never store or log `pw_accounts` personal fields.
- LOE emergency API: `pw_accidents?page=N&otg.id=&city.id=&street.id=`. Fields: `id`, `buildingNames` (comma list like `"5, 9"`), `dateEvent` (start), `datePlanIn` (planned restore), `typeOff`, `koment`.
- Windows console: when inspecting API JSON from bash, decode bytes explicitly (`json.loads(sys.stdin.buffer.read())`) and print with ASCII escapes; Cyrillic otherwise prints garbled.

