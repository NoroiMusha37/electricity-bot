# deploy

## Purpose

- How the bot runs in production: alwaysdata Free plan, as a website of type "User program", kept alive by an external pinger.

## Ownership

- `README.md`: step-by-step guide (account and SSH, copying code, install, site configuration, pinger, account keep-alive, logs, updating, backup).

## Local Contracts

- Production is alwaysdata **Free**: 256 MB RAM (the bot uses ~195 MB), 1 GB disk, no background services (paid only). The bot therefore runs as a "User program" site and must serve HTTP: `HEALTH_HOST`/`HEALTH_PORT` turn on `energy_bot/health.py`.
- Site settings that must stay: working directory `energy-bot` (`.env` and the database live there), Idle time `0`, Environment `HEALTH_HOST=:: HEALTH_PORT=8100 TZ=Europe/Kyiv` (IP/port as shown by alwaysdata's form).
- cron-job.org calls `https://<account>.alwaysdata.net/` every 5 minutes. It restarts the program if alwaysdata stops it.
- Code is copied as a tar of `energy_bot`, `pyproject.toml` and `uv.lock` (never piped through Windows PowerShell 5.1). The repo is never pushed, so there's no `git clone`.
- Python is the server's `/usr/bin/python3.13`; dependencies via `uv sync --frozen --no-dev`.
- Only one bot instance may poll Telegram at a time: stop local copies while the server one runs.
- Rejected hosting options (2026-11-08): Oracle Free Tier signup fails with Oracle's generic error; Google Cloud wants a $10 prepayment to reactivate; home hosting is out because of power outages.

## Work Guidance

- Keep the guide in sync with `.env.example`, `pyproject.toml` (Python version) and `energy_bot/main.py` (entry point).
- Keep memory in mind: new heavy dependencies may push the bot past 256 MB.

## Verification

- `curl -s https://<account>.alwaysdata.net/` prints `ok`, and the newest file under `~/admin/logs/sites/` ends with `Run polling for bot @...` and no errors.

## Child DOX Index

- None
