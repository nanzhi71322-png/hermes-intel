"""市场结构策略 — 复刻 build_market_candidate 与执行过滤器。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """根据 market_state 行生成 long/short 信号。"""
    bias = row.get("market_bias", "unknown")
    score = int(row.get("score", 0) or 0)
    confirm = int(row.get("confirmation_count", 0) or 0)
    price = float(row.get("price") or row.get("close", 0))

    if score < config.min_score or confirm < config.min_confirmation:
        return None

    if bias == "bullish":
        if not _confirm_long_quality(row):
            return None
        return Signal("long", 80, "strong bullish market structure", bar_index, price)

    if bias == "bearish":
        if not _confirm_short_quality(row):
            return None
        return Signal("short", 80, "strong bearish market structure", bar_index, price)

    return None


def _confirm_long_quality(row: dict) -> bool:
    bb = row.get("bb_position")
    brk = row.get("breakout")
    confirm = int(row.get("confirmation_count", 0) or 0)
    score = int(row.get("score", 0) or 0)

    if row.get("market_bias") != "bullish":
        return False
    if bb == "outside_upper":
        return False
    if bb == "upper" and brk != "up":
        return False
    if score < 85 and confirm < 3 and brk != "up":
        return False
    return True


def _confirm_short_quality(row: dict) -> bool:
    bb = row.get("bb_position")
    brk = row.get("breakout")
    if row.get("market_bias") != "bearish":
        return False
    if bb == "outside_lower":
        return False
    if bb == "lower" and brk != "down":
        return False
    return True
