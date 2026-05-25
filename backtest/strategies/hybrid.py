"""混合策略 — 市场结构 + 动量确认（模拟情绪 alpha 过滤）。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal, momentum_direction
from backtest.strategies.market import generate_signal as market_signal


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """市场结构信号必须同向动量确认才执行。"""
    base = market_signal(row, bar_index, config, history)
    if base is None:
        return None

    direction = momentum_direction(row, history)
    if base.action == "long" and direction != "up":
        return None
    if base.action == "short" and direction != "down":
        return None

    return Signal(
        base.action,
        min(95, base.confidence + 5),
        f"hybrid: {base.reason} + momentum confirm",
        bar_index,
        base.price,
    )
