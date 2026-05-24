"""蒙特卡洛模拟 — 对交易序列随机重排评估稳健性。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from backtest.metrics import _max_drawdown


@dataclass
class MonteCarloResult:
    """蒙特卡洛输出摘要。"""

    simulations: int
    median_return_pct: float
    p5_return_pct: float
    p95_return_pct: float
    median_max_dd_pct: float
    p95_max_dd_pct: float
    ruin_rate_pct: float


def run_monte_carlo(
    trade_pnls: list[float],
    starting_balance: float = 100.0,
    simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """随机重排交易 PnL 序列，估计收益分布。"""
    if not trade_pnls:
        return MonteCarloResult(0, 0, 0, 0, 0, 0, 0)

    rng = random.Random(seed)
    returns: list[float] = []
    drawdowns: list[float] = []
    ruin_count = 0

    for _ in range(simulations):
        shuffled = trade_pnls.copy()
        rng.shuffle(shuffled)
        balance = starting_balance
        equity = [balance]
        for pnl in shuffled:
            balance += pnl
            equity.append(balance)
            if balance <= 0:
                ruin_count += 1
                break

        ret_pct = (balance - starting_balance) / starting_balance * 100
        returns.append(ret_pct)
        drawdowns.append(_max_drawdown(equity, starting_balance))

    returns.sort()
    drawdowns.sort()
    n = len(returns)

    return MonteCarloResult(
        simulations=simulations,
        median_return_pct=returns[n // 2],
        p5_return_pct=returns[int(n * 0.05)],
        p95_return_pct=returns[int(n * 0.95)],
        median_max_dd_pct=drawdowns[n // 2],
        p95_max_dd_pct=drawdowns[int(n * 0.95)],
        ruin_rate_pct=ruin_count / simulations * 100,
    )


def monte_carlo_to_dict(result: MonteCarloResult) -> dict[str, Any]:
    """转为可序列化字典。"""
    return {
        "simulations": result.simulations,
        "median_return_pct": round(result.median_return_pct, 2),
        "p5_return_pct": round(result.p5_return_pct, 2),
        "p95_return_pct": round(result.p95_return_pct, 2),
        "median_max_dd_pct": round(result.median_max_dd_pct, 2),
        "p95_max_dd_pct": round(result.p95_max_dd_pct, 2),
        "ruin_rate_pct": round(result.ruin_rate_pct, 2),
    }
