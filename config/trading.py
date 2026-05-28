import config.settings  # noqa: F401  — 确保 dotenv 已加载

import os

TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
TRADING_TESTNET = os.getenv("TRADING_TESTNET", "true").lower() == "true"
TRADING_PAUSED = os.getenv("TRADING_PAUSED", "false").lower() == "true"
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTC/USDT")
DEFAULT_UNDERLYING = os.getenv("DEFAULT_UNDERLYING", "BTCUSDT")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

MAX_POSITION_USD = float(os.getenv("MAX_POSITION_USD", "50"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "20"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))

MIN_BTC_PRICE = float(os.getenv("MIN_BTC_PRICE", "30000"))
MAX_BTC_PRICE = float(os.getenv("MAX_BTC_PRICE", "150000"))

TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.01"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.01"))
POSITION_TTL_SECONDS = int(os.getenv("POSITION_TTL_SECONDS", "300"))
POSITION_MIN_AGE_SECONDS = int(os.getenv("POSITION_MIN_AGE_SECONDS", "30"))

def is_paper_mode() -> bool:
    return TRADING_MODE != "live"

def is_live_mode() -> bool:
    return TRADING_MODE == "live"
