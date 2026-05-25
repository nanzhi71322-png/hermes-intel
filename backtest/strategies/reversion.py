"""均值回归策略 — 布林带极端位置反向入场。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal, momentum_direction


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """超卖反弹 / 超买回落。"""
    bb = row.get("bb_position")
    brk = row.get("breakout")
    price = float(row.get("close", 0) or 0)
    direction = momentum_direction(row, history)

    if bb == "outside_lower" and brk != "down" and direction == "up":
        return Signal("long", 70, "mean reversion from lower band", bar_index, price)

    if bb == "outside_upper" and brk != "up" and direction == "down":
        return Signal("short", 70, "mean reversion from upper band", bar_index, price)

    return None
