"""策略基类与信号定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from backtest.config import BacktestConfig


@dataclass
class Signal:
    """单条交易信号。"""

    action: str
    confidence: int
    reason: str
    bar_index: int
    price: float


class StrategyFn(Protocol):
    """策略函数协议：输入行数据，输出信号或 None。"""

    def __call__(
        self, row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
    ) -> Optional[Signal]:
        ...


def momentum_direction(row: dict, history: dict | None) -> Optional[str]:
    """根据收盘价变化判断动量方向（模拟 live 动量确认）。"""
    if not history:
        return None
    prev_close = history.get("prev_close")
    close = float(row.get("close", 0) or 0)
    if prev_close is None or close <= 0:
        return None
    if close > prev_close * 1.0001:
        return "up"
    if close < prev_close * 0.9999:
        return "down"
    return "flat"
