"""走步验证 — 滚动训练/测试窗口评估策略稳定性。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from loguru import logger

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine
from backtest.metrics import PerformanceMetrics


@dataclass
class WalkForwardFold:
    """单个走步折的结果。"""

    fold: int
    train_bars: int
    test_bars: int
    metrics: PerformanceMetrics


def run_walk_forward(
    df: pd.DataFrame,
    config: BacktestConfig | None = None,
    train_bars: int = 3000,
    test_bars: int = 1000,
    step_bars: int | None = None,
) -> list[WalkForwardFold]:
    """滚动窗口走步验证。"""
    cfg = config or BacktestConfig()
    step = step_bars or test_bars
    folds: list[WalkForwardFold] = []
    fold_idx = 0
    start = 0

    while start + train_bars + test_bars <= len(df):
        test_slice = df.iloc[start + train_bars : start + train_bars + test_bars].copy()
        engine = BacktestEngine(cfg)
        result = engine.run(df=test_slice)
        folds.append(
            WalkForwardFold(
                fold=fold_idx,
                train_bars=train_bars,
                test_bars=len(test_slice),
                metrics=result.metrics,
            )
        )
        logger.info(
            f"走步 fold={fold_idx} 交易={result.metrics.total_trades} "
            f"收益={result.metrics.total_return_pct:.2f}%"
        )
        fold_idx += 1
        start += step

    return folds


def summarize_walk_forward(folds: list[WalkForwardFold]) -> dict[str, Any]:
    """汇总多折走步结果。"""
    if not folds:
        return {"folds": 0}
    returns = [f.metrics.total_return_pct for f in folds]
    sharpes = [f.metrics.sharpe_ratio for f in folds]
    return {
        "folds": len(folds),
        "avg_return_pct": sum(returns) / len(returns),
        "avg_sharpe": sum(sharpes) / len(sharpes),
        "positive_folds": sum(1 for r in returns if r > 0),
    }
