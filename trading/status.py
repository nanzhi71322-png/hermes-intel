"""交易状态汇总（Telegram /tradestatus）。"""
from __future__ import annotations

import asyncio

from config.trading import (
    DEFAULT_SYMBOL,
    MAX_DAILY_LOSS_USD,
    MAX_OPEN_POSITIONS,
    MAX_POSITION_USD,
    TRADING_MODE,
    TRADING_PAUSED,
    TRADING_TESTNET,
    is_live_mode,
)
from trading.exchange.connector import ExchangeConnector
from trading.factory import get_executor
from trading.storage.live_portfolio import load_positions, recent_orders


def _fmt_balance(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def build_trade_status_text() -> str:
    executor = get_executor()
    lines = [
        "Hermes Trade Status",
        f"mode: {TRADING_MODE.upper()}",
        f"executor: {executor.mode}",
        f"testnet: {TRADING_TESTNET}",
        f"paused: {TRADING_PAUSED}",
        f"symbol: {DEFAULT_SYMBOL}",
        f"limits: max_pos=${MAX_POSITION_USD} max_loss=${MAX_DAILY_LOSS_USD} max_open={MAX_OPEN_POSITIONS}",
    ]

    connector = ExchangeConnector()
    try:
        ticker = connector.fetch_ticker(DEFAULT_SYMBOL)
        lines.append(f"price: {ticker.get('last')}")
        if is_live_mode():
            balance = connector.fetch_balance()
            free = balance.get("free", {})
            lines.append(f"USDT free: {_fmt_balance(free.get('USDT'))}")
            lines.append(f"BTC free: {_fmt_balance(free.get('BTC'))}")
    except Exception as exc:
        lines.append(f"exchange: error ({exc})")
    finally:
        connector.close()

    if is_live_mode():
        positions = load_positions()
        lines.append(f"live open: {len(positions)}")
        for idx, pos in enumerate(positions[:3], start=1):
            lines.append(
                f"  {idx}. {pos.get('type')} {pos.get('exchange_symbol')} "
                f"size={pos.get('size')} entry={pos.get('entry_price')} "
                f"order={pos.get('order_id')}"
            )
        orders = recent_orders(3)
        if orders:
            lines.append("recent orders:")
            for order in orders:
                lines.append(
                    f"  - {order.get('side')} {order.get('symbol')} "
                    f"${order.get('size_usd')} id={order.get('order_id')}"
                )
    else:
        import json
        import os

        from intel.paper_trading import PORTFOLIO_FILE

        paper_balance = "n/a"
        paper_open = 0
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                paper_balance = f"{float(payload.get('balance', 0)):.2f}"
                paper_open = len(payload.get("positions", []))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        lines.append(f"paper balance: {paper_balance}")
        lines.append(f"paper open: {paper_open}")

    return "\n".join(lines)


async def build_trade_status_text_async() -> str:
    return await asyncio.to_thread(build_trade_status_text)
