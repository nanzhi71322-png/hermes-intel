# Hermes Telegram Bot

Hermes is a production-oriented Telegram bot for browser automation, crypto intelligence monitoring, autonomous X search scans, and named analyst agents.

The current runtime is implemented in `tg_bot.py`. It uses Telegram polling, Redis-backed memory, DeepSeek chat completions through the OpenAI-compatible SDK, and Playwright persistent Chromium profiles.

## Features

- Telegram chat assistant backed by DeepSeek.
- Browser automation commands for open, search, read, screenshot, click, type, press, scroll, and link extraction.
- Page analysis through `/askpage`.
- One-off crypto intelligence scan through `/intel`.
- Persistent autonomous keyword monitors through `/autonomous`.
- Named crypto intelligence agents through `/agent`.
- Redis signal memory to avoid repeating already-seen page content.
- JSON task persistence so selected autonomous jobs restart with the bot.
- Operational commands for status, logs, memory, disk, Docker, and service restarts.

## Runtime Requirements

- Python 3.12.
- Redis running on `127.0.0.1:6379`.
- Playwright Chromium installed.
- A visible/headful browser environment. The current code runs Chromium with `headless=False`.
- Telegram bot token.
- DeepSeek API key.
- Linux service layout under `/opt/hermes`.

The current code has hard-coded production paths:

- Env file: `/opt/hermes/.env`
- Bot source/state path: `/opt/hermes/tg-bot`
- Logs: `/opt/hermes/logs/tg.log`
- Screenshots: `/opt/hermes/workspace/screenshots`
- Browser profiles: `/opt/hermes/browser-data`
- Chromium binary: `/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome`

## Installation

```bash
cd /opt/hermes/tg-bot
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Create `/opt/hermes/.env`:

```bash
cp .env.example /opt/hermes/.env
```

Then fill in `TELEGRAM_BOT_TOKEN` and `DEEPSEEK_API_KEY`.

## Running

```bash
source /opt/hermes/tg-bot/venv/bin/activate
python /opt/hermes/tg-bot/tg_bot.py
```

For production, run the bot under systemd as `hermes-bot`. The built-in `/status`, `/restartbot`, and `/restartruntime` commands expect systemd units named `hermes-bot` and `hermes`.

## Main Telegram Commands

- `/status`: show `hermes` and `hermes-bot` service status.
- `/memory`: show host memory.
- `/disk`: show disk usage.
- `/docker`: show running Docker containers.
- `/logs`: show recent bot logs.
- `/restartbot`: restart the `hermes-bot` service.
- `/restartruntime`: restart the `hermes` service.
- `/open target`: open a site or URL in the shared browser.
- `/search keyword`: open X search for a keyword.
- `/read`: extract current page text.
- `/screenshot target`: capture a full-page screenshot.
- `/askpage question`: ask the LLM about the current page.
- `/click text`: click visible text.
- `/clickindex n`: click the nth extracted link.
- `/type selector text`: fill a selector.
- `/typeactive text`: type into the active element.
- `/press key`: press a keyboard key.
- `/scroll amount`: scroll the current page.
- `/extractlinks`: list the first 30 page links.
- `/intel keyword`: run a one-off X intelligence brief.
- `/autonomous keyword`: start a persistent keyword monitor.
- `/stopauto keyword`: stop a keyword monitor.
- `/autolist`: list running autonomous tasks.
- `/agents`: list available named agents.
- `/agent name`: start a named agent.
- `/stopagent name`: stop a named agent.
- `/clear_signal_memory keyword`: clear Redis signal memory for a keyword.

## Persistent State

`autonomous_tasks.json` stores the task definitions that should be recreated on startup. Redis stores chat history and signal hashes.

Do not treat `autonomous_tasks.json` as a task health database. It only records intended background jobs.

## Production Notes

- Restrict bot access at the Telegram/chat level before exposing runtime commands.
- Keep Redis local or protected.
- Ensure the browser can run headful Chromium.
- Rotate and monitor `/opt/hermes/logs/tg.log`.
- Back up `/opt/hermes/browser-data` if browser login/session state matters.
- Review [docs/system_architecture.md](docs/system_architecture.md) before refactoring browser, task, or recovery behavior.

## Documentation

- [System architecture](docs/system_architecture.md)
- [Deployment guide](docs/deployment.md)
- [Environment variables](docs/environment.md)
