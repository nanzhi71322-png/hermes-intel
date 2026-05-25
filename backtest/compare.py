"""多策略对比 — 同数据、同周期下横向评估与排名。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from loguru import logger

from backtest.config import BacktestConfig
from backtest.data_loader import load_or_fetch
from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import PerformanceMetrics
from backtest.optimizer import _default_score, optuna_search
from backtest.strategies.registry import STRATEGIES, StrategySpec, get_strategy


@dataclass
class CompareRow:
    """单策略对比行。"""

    strategy: str
    label: str
    timeframe: str
    bars: int
    metrics: PerformanceMetrics
    score: float
    tuned: bool = False
    best_params: dict[str, Any] | None = None


def _score(metrics: PerformanceMetrics) -> float:
    return _default_score(metrics)


def run_single(
    spec: StrategySpec,
    df: pd.DataFrame,
    config_override: BacktestConfig | None = None,
    tuned: bool = False,
    best_params: dict[str, Any] | None = None,
) -> CompareRow:
    """运行单个策略回测。"""
    cfg = config_override or spec.default_config
    engine = BacktestEngine(cfg, strategy_fn=spec.fn, strategy_name=spec.name)
    result = engine.run(df=df)
    params = best_params or {
        "take_profit_pct": cfg.take_profit_pct,
        "stop_loss_pct": cfg.stop_loss_pct,
        "position_ttl_bars": cfg.position_ttl_bars,
        "min_score": cfg.min_score,
        "min_confirmation": cfg.min_confirmation,
        "timeframe": cfg.timeframe,
    }
    return CompareRow(
        strategy=spec.name,
        label=spec.label,
        timeframe=cfg.timeframe,
        bars=result.bars,
        metrics=result.metrics,
        score=_score(result.metrics),
        tuned=tuned,
        best_params=params,
    )


def compare_all(
    strategy_names: list[str] | None = None,
    limit: int = 5000,
    refresh: bool = False,
    auto_tune_top: int = 2,
    tune_trials: int = 15,
) -> list[CompareRow]:
    """对比全部策略；对表现最好的 N 个自动 Optuna 调参后再比一轮。"""
    names = strategy_names or list(STRATEGIES.keys())
    baseline_rows: list[CompareRow] = []
    data_cache: dict[str, pd.DataFrame] = {}

    for name in names:
        spec = get_strategy(name)
        tf = spec.default_config.timeframe
        cache_key = f"{spec.default_config.symbol}_{tf}"
        if cache_key not in data_cache:
            data_cache[cache_key] = load_or_fetch(
                spec.default_config.symbol,
                tf,
                limit=limit,
                refresh=refresh,
            )
        row = run_single(spec, data_cache[cache_key])
        baseline_rows.append(row)
        logger.info(
            f"基线 | {row.label} | trades={row.metrics.total_trades} "
            f"ret={row.metrics.total_return_pct:.2f}% score={row.score:.2f}"
        )

    ranked = sorted(baseline_rows, key=lambda r: r.score, reverse=True)
    tuned_rows: list[CompareRow] = []

    for candidate in ranked[:auto_tune_top]:
        if candidate.metrics.total_trades < 3:
            continue
        spec = get_strategy(candidate.strategy)
        df = data_cache[f"{spec.default_config.symbol}_{spec.default_config.timeframe}"]
        opt = optuna_search(df, n_trials=tune_trials, base_config=spec.default_config)
        cfg = spec.default_config
        for key, val in opt.best_params.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)
        tuned = run_single(spec, df, config_override=cfg, tuned=True, best_params=opt.best_params)
        tuned_rows.append(tuned)
        logger.info(
            f"调参 | {tuned.label} | ret={tuned.metrics.total_return_pct:.2f}% "
            f"score={tuned.score:.2f} params={opt.best_params}"
        )

    final = baseline_rows.copy()
    for tuned in tuned_rows:
        final = [r for r in final if r.strategy != tuned.strategy]
        final.append(tuned)

    return sorted(final, key=lambda r: r.score, reverse=True)


def rows_to_dict(rows: list[CompareRow]) -> list[dict[str, Any]]:
    """序列化对比结果。"""
    output = []
    for row in rows:
        output.append(
            {
                "strategy": row.strategy,
                "label": row.label,
                "timeframe": row.timeframe,
                "bars": row.bars,
                "tuned": row.tuned,
                "score": round(row.score, 4),
                "best_params": row.best_params,
                "metrics": row.metrics.__dict__,
            }
        )
    return output
