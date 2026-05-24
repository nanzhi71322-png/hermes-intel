"""绩效评估 — 夏普、最大回撤、胜率、盈亏比等。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backtest.portfolio import BacktestPortfolio


@dataclass
class PerformanceMetrics:
    """策略绩效摘要。"""

    total_trades: int
    win_trades: int
    win_rate: float
    total_pnl: float
    total_return_pct: float
    avg_pnl: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    avg_win: float
    avg_loss: float
    payoff_ratio: float


def compute_metrics(portfolio: "BacktestPortfolio", starting_balance: float) -> PerformanceMetrics:
    """从持仓对象计算全套绩效指标。"""
    trades = portfolio.closed_trades
    total = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    total_pnl = sum(t.pnl for t in trades)
    win_rate = (len(wins) / total * 100) if total else 0.0
    avg_pnl = (total_pnl / total) if total else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    returns = [t.pnl / starting_balance for t in trades]
    sharpe = _sharpe(returns)
    max_dd = _max_drawdown(portfolio.equity_curve, starting_balance)
    ret_pct = ((portfolio.balance - starting_balance) / starting_balance) * 100

    return PerformanceMetrics(
        total_trades=total,
        win_trades=len(wins),
        win_rate=win_rate,
        total_pnl=total_pnl,
        total_return_pct=ret_pct,
        avg_pnl=avg_pnl,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff,
    )


def _sharpe(returns: list[float], annual_factor: float = 252.0) -> float:
    """简化夏普比率（按交易序列）。"""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(annual_factor)


def _max_drawdown(equity: list[float], starting: float) -> float:
    """计算最大回撤百分比。"""
    if not equity:
        return 0.0
    peak = starting
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        dd = (peak - value) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd
