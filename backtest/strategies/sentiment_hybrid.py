"""情绪+结构双过滤 — sentiment_proxy 与 market 结构同时确认。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal
from backtest.strategies import market, sentiment_proxy


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """两套逻辑同时出 long/short 才入场。"""
    sent = sentiment_proxy.generate_signal(row, bar_index, config, history)
    struct = market.generate_signal(row, bar_index, config, history)
    if not sent or not struct:
        return None
    if sent.action != struct.action:
        return None
    return Signal(
        sent.action,
        min(95, sent.confidence + 3),
        f"sentiment+structure: {sent.reason}",
        bar_index,
        sent.price,
    )
