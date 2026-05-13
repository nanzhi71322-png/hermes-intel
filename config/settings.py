from dotenv import load_dotenv
load_dotenv()

import os


ENV_FILE = os.getenv("ENV_FILE", "/opt/hermes/.env")

HERMES_HOME = os.getenv("HERMES_HOME", "/opt/hermes")
BOT_HOME = os.getenv("BOT_HOME", "/opt/hermes/tg-bot")

LOG_DIR = os.getenv("LOG_DIR", "/opt/hermes/logs")
LOG_FILE = os.getenv("LOG_FILE", "/opt/hermes/logs/tg.log")

SCREENSHOT_DIR = os.getenv(
    "SCREENSHOT_DIR",
    "/opt/hermes/workspace/screenshots"
)

BROWSER_DATA_DIR = os.getenv(
    "BROWSER_DATA_DIR",
    "/opt/hermes/browser-data"
)

DEFAULT_BROWSER_DATA_DIR = os.getenv(
    "DEFAULT_BROWSER_DATA_DIR",
    "/opt/hermes/browser-data/default"
)

CHROMIUM_EXECUTABLE = os.getenv(
    "CHROMIUM_EXECUTABLE",
    "/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
)

TASKS_FILE = os.getenv(
    "TASKS_FILE",
    "/opt/hermes/tg-bot/autonomous_tasks.json"
)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_TOKEN = TELEGRAM_BOT_TOKEN

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com"
)
DEEPSEEK_MODEL = os.getenv(
    "DEEPSEEK_MODEL",
    "deepseek-chat"
)


def ensure_runtime_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
    os.makedirs(DEFAULT_BROWSER_DATA_DIR, exist_ok=True)