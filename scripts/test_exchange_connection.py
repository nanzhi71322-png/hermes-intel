"""Test Binance Testnet connection via CCXT."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.deploy.local")
load_dotenv(os.getenv("ENV_FILE", "/opt/hermes/.env"))

from trading.exchange.connector import ExchangeConnector


def main() -> None:
    connector = ExchangeConnector()
    try:
        ticker = connector.fetch_ticker("BTC/USDT")
        balance = connector.fetch_balance()
        usdt_free = balance.get("free", {}).get("USDT")
        btc_free = balance.get("free", {}).get("BTC")
        print("CONNECTION_OK")
        print(f"BTC/USDT last={ticker.get('last')}")
        print(f"USDT free={usdt_free}")
        print(f"BTC free={btc_free}")
    finally:
        connector.close()


if __name__ == "__main__":
    main()
