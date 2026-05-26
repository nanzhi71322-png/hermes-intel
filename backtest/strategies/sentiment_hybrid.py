"""情绪+结构双过滤 — sentiment_proxy 与 market 结构同时确认。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal
from backtest.strategies import market, sentiment_proxy


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """strict: 情绪+结构同向；soft: 高置信情绪可单独入场。"""
    sent = sentiment_proxy.generate_signal(row, bar_index, config, history)
    struct = market.generate_signal(row, bar_index, config, history)
    mode = str(config.extra.get("dual_mode", "strict"))

    if sent and struct and sent.action == struct.action:
        return Signal(
            sent.action,
            min(95, sent.confidence + 3),
            f"sentiment+structure: {sent.reason}",
            bar_index,
            sent.price,
        )

    if mode != "soft" or not sent:
        return None

    soft_min = int(config.extra.get("soft_min_confidence", 78))
    if int(sent.confidence) < soft_min:
        return None
    if struct is not None and struct.action != sent.action:
        return None
    return Signal(
        sent.action,
        sent.confidence,
        f"sentiment-soft: {sent.reason}",
        bar_index,
        sent.price,
    )
