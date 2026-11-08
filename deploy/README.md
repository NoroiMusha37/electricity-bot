# Deployment on alwaysdata (free plan)

The bot runs on [alwaysdata](https://www.alwaysdata.com/en/offers/)'s **Free** plan (1 GB disk, 256 MB RAM,
no card) as a website of type **User program**. The free plan has no background "services", so the bot also
serves a tiny "ok" web endpoint (`energy_bot/health.py`), and a free external pinger
([cron-job.org](https://cron-job.org)) calls it every 5 minutes. If alwaysdata ever stops the program, the next
ping starts it again.

Measured footprint: about **195 MB RAM** (of 256) and about 60 MB of disk.

In the commands below, replace `<account>` with your alwaysdata account name.

## 1. Account and SSH

1. Sign up for the **Free** plan at https://www.alwaysdata.com/en/offers/.
2. In the admin panel, **Remote access → SSH/SFTP** shows the SSH user (your account name), the host
   `ssh-<account>.alwaysdata.net` and whether a password is active (the key icon sets one).

```bash
ssh <account>@ssh-<account>.alwaysdata.net
```

## 2. Copy the bot

On your computer, in PowerShell, from the project folder. This packs only what the bot needs (no `.env`, no
database, no `.venv`) and uploads it together with `.env`:

```powershell
tar -cf "$env:TEMP\energy-bot.tar" --exclude=__pycache__ energy_bot pyproject.toml uv.lock
scp "$env:TEMP\energy-bot.tar" .env <account>@ssh-<account>.alwaysdata.net:~/
```

Don't pipe archives through `|` in Windows PowerShell 5.1: it treats the data as text and corrupts it.

On the server:

```bash
mkdir -p ~/energy-bot && tar -xf ~/energy-bot.tar -C ~/energy-bot && rm ~/energy-bot.tar
mv ~/.env ~/energy-bot/.env && chmod 600 ~/energy-bot/.env
```

## 3. Install

On the server (Python 3.13 is preinstalled as `/usr/bin/python3.13`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/energy-bot && uv sync --frozen --no-dev --python /usr/bin/python3.13
```

Optional check by hand (stop any other running copy of the bot first; only one may poll Telegram):

```bash
.venv/bin/python -m energy_bot.main
```

Wait for `Run polling for bot @...`, then stop it with `Ctrl+C`.

## 4. Run it as a site

The account comes with a default site on `<account>.alwaysdata.net`; turn it into the bot.
**Web → Sites → ⚙️ on that site**:

| Field             | Value                                                                       |
|-------------------|-----------------------------------------------------------------------------|
| Type              | User program                                                                |
| Command           | `/home/<account>/energy-bot/.venv/bin/python -m energy_bot.main`          |
| Working directory | `energy-bot` (the bot reads `.env` and keeps its database there)            |
| Environment       | `HEALTH_HOST=:: HEALTH_PORT=8100 TZ=Europe/Kyiv`                            |
| Hot restart       | Unsupported                                                                 |

Use the IP and port the form's help text shows: `::` and `8100` at the time of writing (alwaysdata also puts them
into the `IP`/`PORT` variables). `TZ` only makes log timestamps Kyiv time; the bot's logic always uses
Europe/Kyiv.

Then, on the site's **ADVANCED** tab, set **Idle time** to `0` (never stop for inactivity) and submit.

Check it from SSH; the `curl` should print `ok`:

```bash
curl -s https://<account>.alwaysdata.net/; echo
tail -n 5 "$(find ~/admin/logs/sites -type f | sort | tail -1)"
```

The log should end with `Run polling for bot @...`. The bot runs on alwaysdata's web servers, not on the SSH
host, so `ps` over SSH won't show it.

## 5. The pinger

At https://cron-job.org (free account), **Create cronjob**: URL `https://<account>.alwaysdata.net/`, every
**5 minutes**. Its history should show status 200.

## Keep the account alive

Free accounts are suspended if nobody logs in to the admin panel for **120 days** (accounts older than a year:
6 months). Logging in lifts a suspension immediately
([details](https://help.alwaysdata.com/en/docs/admin-billing/profile/suspension/)).

## Logs and memory

- Bot log: `tail -f "$(find ~/admin/logs/sites -type f | sort | tail -1)"` (files are grouped by date).
- Memory: the admin panel's **Usage** page. The bot needs about 195 MB of the 256 MB limit.

## Updating

Repeat step 2 (copy). Run `uv sync --frozen --no-dev --python /usr/bin/python3.13` if dependencies changed.
Then restart the site (Web → Sites, or save its configuration again) so it runs the new code.

## Backup

The only state is `~/energy-bot/energy_bot.db`. Python's SQLite backup makes a consistent copy even while the
bot is running:

```bash
cd ~/energy-bot && .venv/bin/python -c "import sqlite3; sqlite3.connect('energy_bot.db').backup(sqlite3.connect('backup.db'))"
```

Then download it from your computer:

```powershell
scp <account>@ssh-<account>.alwaysdata.net:~/energy-bot/backup.db .
```
