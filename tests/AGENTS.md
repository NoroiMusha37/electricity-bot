# tests

## Purpose

- pytest suite for the parser, warning timing, accident diffing and the LOE client.

## Ownership

- `fixtures/`: real samples captured from the LOE APIs on 2026-11-06, trimmed and stripped of any personal data:
  - `schedule_single.html`, `schedule_multi.html` (up to 5 intervals, 24:00), `schedule_glitch.html` (00:00–00:00 placeholders);
  - `menus.json` (Today filled, Tomorrow empty);
  - `accidents.json` (12 real records);
  - `cities.json`, `streets.json`, `accounts.json` (only `buildingName`/`chergGpv` kept).
- `conftest.py`: `KYIV` tz, `fixture_text(name)`, `fixture_json(name)`. Import them as `from tests.conftest import ...`.
- `test_*.py`: one file per unit under test.

## Local Contracts

- Tests never hit the network. HTTP is mocked with `respx`.
- Test only our own logic. Every branch should be covered, but don't test library behaviour (pydantic parsing, default values), assertions that can't fail (e.g. what a validator already guarantees), or things another test already covers.
- Time-dependent tests inject `now` explicitly (Europe/Kyiv), never the wall clock.

## Work Guidance

- `asyncio_mode = "auto"` (pyproject): async tests need no decorator.
- Settings tests `monkeypatch.chdir(tmp_path)` and set env vars via `monkeypatch`, so a local `.env` never leaks in.

## Verification

- `uv run pytest`

## Child DOX Index

- None
