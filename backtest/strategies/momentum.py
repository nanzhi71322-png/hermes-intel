"""动量突破策略 — 量价突破 + 方向确认。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """突破 + 放量 + K 线方向一致时入场。"""
    brk = row.get("breakout")
    vol_ratio = row.get("volume_ratio_1m")
    price = float(row.get("close", 0) or 0)
    open_price = float(row.get("open", price) or price)

    min_vol = float(config.extra.get("min_volume_ratio", 1.3))
    if vol_ratio is None or vol_ratio < min_vol:
        return None

    if brk == "up" and open_price < price:
        return Signal("long", 75, "momentum breakout up with volume", bar_index, price)

    if brk == "down" and open_price > price:
        return Signal("short", 75, "momentum breakout down with volume", bar_index, price)

    return None
