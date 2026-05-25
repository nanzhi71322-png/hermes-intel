"""市场结构策略 — 兼容旧 import，实际逻辑在 strategies/market.py。"""

from backtest.strategies.base import Signal
from backtest.strategies.market import generate_signal

__all__ = ["Signal", "generate_signal"]
