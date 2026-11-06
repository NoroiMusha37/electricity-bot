# tests

## Purpose

- pytest suite for the parser, warning timing, accident diffing and the LOE client.

## Ownership

- `fixtures/`: real samples captured from the LOE APIs (schedule `rawHtml`, `pw_accidents` JSON), stripped of any personal data.
- `test_*.py`: one file per unit under test.

## Local Contracts

- Tests never hit the network. HTTP is mocked with `respx`.
- Time-dependent tests inject `now` explicitly (Europe/Kyiv), never the wall clock.

## Work Guidance

- `asyncio_mode = "auto"` (pyproject): async tests need no decorator.
- Settings tests `monkeypatch.chdir(tmp_path)` and set env vars via `monkeypatch`, so a local `.env` never leaks in.

## Verification

- `uv run pytest`

## Child DOX Index

- None
