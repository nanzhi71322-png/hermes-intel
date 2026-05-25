"""参数优化 — 网格搜索与 Optuna 贝叶斯优化。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from loguru import logger

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine


@dataclass
class OptimizationResult:
    """优化最优参数与得分。"""

    best_params: dict[str, Any]
    best_score: float
    trials: list[dict[str, Any]]


def grid_search(
    df: pd.DataFrame,
    param_grid: dict[str, list[Any]],
    score_fn: Callable | None = None,
    base_config: BacktestConfig | None = None,
) -> OptimizationResult:
    """穷举网格搜索最优参数组合。"""
    score_fn = score_fn or _default_score
    base = base_config or BacktestConfig()
    trials: list[dict[str, Any]] = []
    best_score = float("-inf")
    best_params: dict[str, Any] = {}

    keys = list(param_grid.keys())
    combos = _product(param_grid)

    for combo in combos:
        params = dict(zip(keys, combo))
        cfg = _apply_params(base, params)
        result = BacktestEngine(cfg).run(df=df)
        score = score_fn(result.metrics)
        trial = {"params": params, "score": score, "metrics": result.metrics}
        trials.append(trial)
        if score > best_score:
            best_score = score
            best_params = params

    logger.info(f"网格搜索完成 | 最优得分={best_score:.4f} 参数={best_params}")
    return OptimizationResult(best_params=best_params, best_score=best_score, trials=trials)


def optuna_search(
    df: pd.DataFrame,
    n_trials: int = 30,
    base_config: BacktestConfig | None = None,
) -> OptimizationResult:
    """Optuna 贝叶斯优化 TP/SL/确认阈值。"""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    base = base_config or BacktestConfig()
    trials_log: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        params = {
            "take_profit_pct": trial.suggest_float("take_profit_pct", 0.005, 0.03),
            "stop_loss_pct": trial.suggest_float("stop_loss_pct", 0.005, 0.03),
            "position_ttl_bars": trial.suggest_int("position_ttl_bars", 3, 30),
            "min_score": trial.suggest_int("min_score", 70, 90),
            "min_confirmation": trial.suggest_int("min_confirmation", 2, 4),
        }
        cfg = _apply_params(base, params)
        result = BacktestEngine(cfg).run(df=df)
        score = _default_score(result.metrics)
        trials_log.append({"params": params, "score": score})
        return score

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

    return OptimizationResult(
        best_params=study.best_params,
        best_score=study.best_value,
        trials=trials_log,
    )


def _default_score(metrics) -> float:
    """综合评分：收益 - 回撤惩罚 + 夏普奖励。"""
    if metrics.total_trades < 5:
        return -999.0
    return (
        metrics.total_return_pct
        - metrics.max_drawdown_pct * 0.5
        + metrics.sharpe_ratio * 2
    )


def _apply_params(base: BacktestConfig, params: dict[str, Any]) -> BacktestConfig:
    """从基础配置复制并覆盖参数。"""
    data = base.to_dict()
    data.update(params)
    return BacktestConfig(**{k: v for k, v in data.items() if hasattr(BacktestConfig, k)})


def _product(grid: dict[str, list[Any]]) -> list[tuple]:
    """笛卡尔积。"""
    keys = list(grid.keys())
    if not keys:
        return [()]
    result: list[tuple] = [()]
    for key in keys:
        result = [r + (val,) for r in result for val in grid[key]]
    return result
