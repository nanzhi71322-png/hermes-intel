# Refactor Plan and Migration Report

## Approved Scope

Phase 1 only:

- `config`
- `utils`
- `memory`

Explicitly not changed in this phase:

- Autonomous task module structure.
- Telegram command handler module structure.
- Agent loop module structure.
- Browser module structure beyond importing extracted config/utility values.

## Dependency Map

Current runtime dependencies after Phase 1:

```text
tg_bot.py
  -> config.settings
  -> config.clients
  -> memory.chat
  -> memory.signals
  -> utils.logging
  -> utils.urls
  -> Playwright
  -> Telegram handlers
  -> autonomous loops still local
  -> agent loops still local

config.settings
  -> os
  -> python-dotenv

config.clients
  -> redis
  -> openai
  -> config.settings

memory.chat
  -> config.clients
  -> config.settings

memory.signals
  -> hashlib
  -> config.clients

utils.logging
  -> loguru
  -> config.settings

utils.urls
  -> no external dependencies
```

## Module Split Plan

Created package directories:

- `agents`
- `autonomous`
- `browser`
- `commands`
- `config`
- `intel`
- `memory`
- `utils`

Added `__init__.py` to each package so later phases can move code incrementally without changing import style again.

Phase 1 extracted:

- `config/settings.py`
  - Env loading from `/opt/hermes/.env`.
  - Runtime paths.
  - Redis, DeepSeek, model, browser executable constants.
  - `ensure_runtime_dirs()`.

- `config/clients.py`
  - Redis client as `redis_client`.
  - OpenAI-compatible DeepSeek client as `llm_client`.

- `utils/logging.py`
  - `setup_logging()`.

- `utils/urls.py`
  - `normalize_browser_target()`.
  - `build_x_search_url()`.

- `memory/chat.py`
  - `SYSTEM_PROMPT`.
  - `ask_llm()`.
  - Redis chat history behavior preserved.

- `memory/signals.py`
  - `SIGNAL_MEMORY_PREFIX`.
  - `SIGNAL_MEMORY_TTL_SECONDS`.
  - `signal_hash()`.
  - `filter_new_signals()`.
  - Redis signal deduplication behavior preserved.

## Migration Order

Completed:

1. Created target package directories and package markers.
2. Extracted configuration constants and env loading.
3. Extracted Redis and DeepSeek client construction.
4. Extracted logging setup.
5. Extracted URL helper functions.
6. Extracted chat memory and LLM chat helper.
7. Extracted signal memory hashing and deduplication.
8. Rewired `tg_bot.py` imports to use extracted modules.
9. Preserved all Telegram handlers and autonomous/agent loops in `tg_bot.py`.
10. Ran compile verification.

Next recommended phase:

1. Extract browser manager into `browser/manager.py`.
2. Keep command handlers in `tg_bot.py` during that browser extraction.
3. Compile and smoke-test command registration again before moving handlers.

## Changed Imports

Removed from `tg_bot.py`:

```python
import redis
import requests
import hashlib
from urllib.parse import urlparse
from dotenv import load_dotenv
from openai import OpenAI
```

Kept in `tg_bot.py` because still used by local browser, task, and command code:

```python
import os
import subprocess
import asyncio
import json
from datetime import datetime
from loguru import logger
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
```

Added to `tg_bot.py`:

```python
from config.clients import llm_client as client, redis_client as r
from config.settings import (
    BOT_TOKEN,
    BROWSER_DATA_DIR,
    CHROMIUM_EXECUTABLE,
    DEFAULT_BROWSER_DATA_DIR,
    DEEPSEEK_MODEL,
    LOG_FILE,
    SCREENSHOT_DIR,
    TASKS_FILE,
    ensure_runtime_dirs,
)
from memory.chat import ask_llm
from memory.signals import SIGNAL_MEMORY_PREFIX, filter_new_signals
from utils.logging import setup_logging
from utils.urls import build_x_search_url, normalize_browser_target
```

## Dependency Updates

No package dependency changes were required.

Runtime behavior moved, but dependency ownership changed:

- Redis construction moved from `tg_bot.py` to `config.clients`.
- DeepSeek/OpenAI client construction moved from `tg_bot.py` to `config.clients`.
- Dotenv loading moved from `tg_bot.py` to `config.settings`.
- Loguru file setup moved from `tg_bot.py` to `utils.logging`.
- Chat memory moved from `tg_bot.py` to `memory.chat`.
- Signal memory moved from `tg_bot.py` to `memory.signals`.
- URL normalization and X search URL construction moved from inline code to `utils.urls`.

## Verification

Command run:

```bash
python -m py_compile tg_bot.py config/__init__.py config/settings.py config/clients.py utils/__init__.py utils/logging.py utils/urls.py memory/__init__.py memory/chat.py memory/signals.py agents/__init__.py browser/__init__.py commands/__init__.py intel/__init__.py autonomous/__init__.py
```

Result:

```text
passed
```

The first compile attempt failed because Python was denied permission to write `__pycache__`; rerunning with approved permission passed.

## Risk Analysis

Residual risks after Phase 1:

- `tg_bot.py` still contains browser globals, all Telegram handlers, autonomous loops, agent loops, and task persistence. That is intentional for Phase 1 but means the main file is still large.
- Import-time clients are still created during module import, matching previous behavior. This preserves behavior but keeps tests/imports dependent on Redis/OpenAI client construction.
- `config.settings` still preserves hard-coded `/opt/hermes` paths. This avoids behavior drift but does not improve portability yet.
- `client` and `r` aliases remain in `tg_bot.py` to reduce churn. Later phases should replace them with clearer service imports.
- `utils.urls.build_x_search_url()` preserves the previous simple space-to-`%20` behavior. It does not introduce full URL encoding yet, by design.
- Browser recovery behavior is preserved, including the existing mismatch where `agent_loop()` resets an agent browser pool while active agents still use the shared default browser.
- No Telegram live smoke test was run in this phase; verification was limited to static compile.

## Phase 1 Summary

Phase 1 completed without changing Telegram command registration, autonomous task restore flow, agent profiles, Playwright lifecycle structure, or self-healing logic.

The entrypoint now imports configuration, clients, logging setup, URL helpers, chat memory, and signal memory from modular packages. This prepares the codebase for the next low-risk extraction: browser lifecycle and browser tools.

## Phase 2 Migration Report

Scope completed:

- Created `browser/__init__.py`.
- Created `browser/manager.py`.
- Moved browser state into `browser/manager.py`:
  - `playwright_instance`
  - `browser_context`
  - `browser_page`
  - `browser_pool`
  - `browser_lock`
- Moved browser functions into `browser/manager.py`:
  - `init_browser()`
  - `get_agent_page()`
  - `reset_agent_browser()`
  - `browser_open()`
  - `browser_screenshot()`

`tg_bot.py` changes were limited to browser imports and references needed to use the moved state:

```python
import browser.manager as browser_manager
from browser.manager import (
    browser_open,
    browser_screenshot,
    init_browser,
    reset_agent_browser,
)
```

Direct browser page and lock references now use the manager module:

```python
browser_manager.browser_page
browser_manager.browser_lock
```

This preserves the single shared logged-in browser behavior because all command handlers, autonomous loops, and agent loops still point to the same module-level Playwright context and page.

Preserved behavior:

- Default persistent browser profile.
- Per-agent browser pool functions.
- Existing self-healing call to `reset_agent_browser(f"agent_{name}")`.
- Existing screenshot path behavior via `SCREENSHOT_DIR`.
- Existing browser wait times, navigation timeouts, headful Chromium launch args, and returned text formats.
- Existing Telegram command registration.
- Existing autonomous and agent loop logic, except references to moved browser state/functions.

Verification:

```bash
python -m py_compile tg_bot.py browser/__init__.py browser/manager.py
```

Result:

```text
passed
```

Residual risks:

- `tg_bot.py` still contains Telegram command handlers, autonomous task persistence, autonomous loops, and agent loops.
- Runtime browser behavior was not live-smoke-tested against Telegram or Playwright; verification was static compile only.
- The known browser recovery mismatch is preserved: agent self-healing resets the per-agent browser pool while `agent_loop()` still uses the shared default browser page.
- Browser globals remain module-level in `browser.manager`, matching previous behavior but still limiting test isolation.

## Phase 3 Migration Report

Scope completed:

- Created `commands/browser_commands.py`.
- Created `commands/agent_commands.py`.
- Created `commands/autonomous_commands.py`.
- Created `commands/system_commands.py`.
- Replaced `commands/__init__.py` with centralized handler registration.
- Removed Telegram command handler bodies from `tg_bot.py`.
- Replaced inline `app.add_handler(...)` calls with `register_handlers(...)`.

Preserved Telegram commands:

- `/status`
- `/memory`
- `/disk`
- `/docker`
- `/logs`
- `/restartbot`
- `/restartruntime`
- `/open`
- `/search`
- `/read`
- `/scroll`
- `/extractlinks`
- `/clickindex`
- `/askpage`
- `/intel`
- `/autonomous`
- `/stopauto`
- `/autolist`
- `/agent`
- `/stopagent`
- `/agents`
- `/clear_signal_memory`
- `/screenshot`
- `/click`
- `/type`
- `/press`
- `/typeactive`

Also preserved the non-command text message handler by moving it to `commands/system_commands.py`.

Dependency wiring:

- `commands.autonomous_commands.configure(...)` receives:
  - `autonomous_tasks`
  - `autonomous_loop`
  - `save_autonomous_tasks`

- `commands.agent_commands.configure(...)` receives:
  - `autonomous_tasks`
  - `agent_loop`
  - `save_autonomous_tasks`
  - `AGENT_PROFILES`

This avoids importing `tg_bot.py` from command modules and avoids circular imports while keeping autonomous and agent loop behavior in place for this phase.

`tg_bot.py` now handles:

- App construction.
- Handler registration delegation.
- Autonomous task restore scheduling.
- Polling startup.
- Existing autonomous and agent runtime logic that is not approved for extraction yet.

Preserved behavior:

- Autonomous restore still runs after handler registration through `restore_autonomous_tasks()`.
- Self-healing remains in `agent_loop()`.
- Browser state remains in `browser.manager`.
- Redis chat memory remains in `memory.chat`.
- Signal memory remains in `memory.signals`.
- Command names and usage strings were copied from the previous handlers.

Verification:

```bash
python -m py_compile tg_bot.py commands/__init__.py commands/browser_commands.py commands/agent_commands.py commands/autonomous_commands.py commands/system_commands.py
```

Result:

```text
passed
```

Residual risks:

- `tg_bot.py` is slimmer but not fully entrypoint-only yet because autonomous loops, agent loops, profiles, and task persistence are intentionally left there until their approved phases.
- Command modules use dependency injection for autonomous and agent command state. If `register_handlers(...)` is not called before those commands are used, the injected module globals would be unset. The current entrypoint calls registration before polling, preserving runtime behavior.
- Runtime behavior was not live-tested against Telegram; verification was static compile only.
- `/intel` lives in `commands/browser_commands.py` for this phase because the `intel/` package was explicitly out of scope.
