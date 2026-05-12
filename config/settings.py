import os

from dotenv import load_dotenv


ENV_FILE = "/opt/hermes/.env"
HERMES_HOME = "/opt/hermes"
BOT_HOME = "/opt/hermes/tg-bot"
LOG_DIR = "/opt/hermes/logs"
LOG_FILE = "/opt/hermes/logs/tg.log"
SCREENSHOT_DIR = "/opt/hermes/workspace/screenshots"
BROWSER_DATA_DIR = "/opt/hermes/browser-data"
DEFAULT_BROWSER_DATA_DIR = "/opt/hermes/browser-data/default"
CHROMIUM_EXECUTABLE = "/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
TASKS_FILE = "/opt/hermes/tg-bot/autonomous_tasks.json"

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")


def ensure_runtime_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(DEFAULT_BROWSER_DATA_DIR, exist_ok=True)
