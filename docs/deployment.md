# Deployment Guide

This guide deploys the current Hermes Telegram bot implementation as it exists today. Several paths are hard-coded in `tg_bot.py`, so the production layout should match `/opt/hermes`.

## 1. Prepare Host

Install system packages for Python, Redis, and headful browser execution.

Recommended Python version:

- Production: Python 3.12.
- Local Windows/Python 3.13: use `python-telegram-bot==22.7` or newer. Older 20.x releases can fail during `ApplicationBuilder().token(...).build()` with `AttributeError: 'Updater' object has no attribute '_Updater__polling_cleanup_cb'`.
- Only one polling instance can run for a bot token.

```bash
sudo mkdir -p /opt/hermes/tg-bot
sudo mkdir -p /opt/hermes/logs
sudo mkdir -p /opt/hermes/workspace/screenshots
sudo mkdir -p /opt/hermes/browser-data/default
```

Redis must be reachable at:

```text
127.0.0.1:6379
```

The current code does not read Redis host, port, or password from environment variables.

## 2. Install Application

Place this repository at:

```text
/opt/hermes/tg-bot
```

Install Python dependencies:

```bash
cd /opt/hermes/tg-bot
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

The code currently points directly to this Chromium executable:

```text
/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome
```

If Playwright installs a different Chromium revision, either install the expected revision or update `executable_path` in `tg_bot.py`.

## 3. Configure Secrets

Create the runtime env file:

```bash
cp /opt/hermes/tg-bot/.env.example /opt/hermes/.env
chmod 600 /opt/hermes/.env
```

Edit `/opt/hermes/.env` and set:

```bash
TELEGRAM_BOT_TOKEN=...
DEEPSEEK_API_KEY=...
```

## 4. Smoke Test

Run the bot manually first:

```bash
cd /opt/hermes/tg-bot
source venv/bin/activate
python tg_bot.py
```

From Telegram, test:

- `/memory`
- `/disk`
- `/agents`
- a plain chat message
- `/open example.com`

If browser commands fail, check:

- Chromium executable path.
- Display/X server availability.
- Permissions for `/opt/hermes/browser-data`.
- Redis availability.
- `/opt/hermes/logs/tg.log`.

## 5. systemd Service

Create `/etc/systemd/system/hermes-bot.service`:

```ini
[Unit]
Description=Hermes Telegram Bot
After=network-online.target redis.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/hermes/tg-bot
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/hermes/tg-bot/venv/bin/python /opt/hermes/tg-bot/tg_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-bot
sudo systemctl start hermes-bot
sudo systemctl status hermes-bot --no-pager
```

The bot's `/status` command also references a `hermes` service. If you do not have a separate runtime service named `hermes`, `/status` and `/restartruntime` will partially fail or report that unit as missing.

## 6. Operational Checks

Use these checks after deployment:

```bash
systemctl status hermes-bot --no-pager
tail -100 /opt/hermes/logs/tg.log
redis-cli ping
ls -la /opt/hermes/browser-data
ls -la /opt/hermes/workspace/screenshots
```

Telegram checks:

- `/status`
- `/logs`
- `/autolist`
- `/agent btc`
- `/stopagent btc`

## 7. Persistence

Autonomous and agent tasks are saved in:

```text
/opt/hermes/tg-bot/autonomous_tasks.json
```

On bot restart, `restore_autonomous_tasks()` recreates tasks from that file.

Redis stores:

- `memory:{user_id}` chat history.
- `signal_memory:{keyword}` deduplication hashes.

Signal memory expires after seven days.

## 8. Backup Targets

Back up these paths if the instance is stateful:

- `/opt/hermes/.env`
- `/opt/hermes/tg-bot/autonomous_tasks.json`
- `/opt/hermes/browser-data`

Logs and screenshots may be useful for debugging but can become large:

- `/opt/hermes/logs`
- `/opt/hermes/workspace/screenshots`

## 9. Production Hardening

Recommended before exposing the bot broadly:

- Add a Telegram chat/user allowlist.
- Move hard-coded paths into environment variables.
- Protect runtime commands such as `/restartbot`, `/restartruntime`, `/docker`, and `/logs`.
- Use an async LLM client or run blocking calls off the event loop.
- Add a default browser reset path.
- Add task health metadata and supervision.
- Add log and screenshot retention policy.
