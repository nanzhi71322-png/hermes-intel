"""并行回测 — 同批候选同时跑，大幅缩短筛选时间。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import pandas as pd
from loguru import logger

from backtest.candidate import StrategyCandidate
from backtest.compare import CompareRow, run_single
from backtest.config_utils import config_key
from backtest.data_loader import load_or_fetch
from backtest.strategies.registry import get_strategy


def _run_one(candidate: StrategyCandidate, df: pd.DataFrame) -> CompareRow:
    spec = get_strategy(candidate.strategy)
    row = run_single(
        spec,
        df,
        config_override=candidate.config,
        tuned=bool(candidate.params),
        best_params=candidate.params or None,
    )
    row.label = f"{row.label}[{candidate.candidate_id}]"
    return row


def run_parallel(
    candidates: list[StrategyCandidate],
    limit: int = 5000,
    refresh: bool = False,
    workers: int = 6,
    progress: Callable[[int, int], None] | None = None,
) -> list[CompareRow]:
    """并行执行候选列表，按数据周期分组缓存 K 线。"""
    data_cache: dict[str, pd.DataFrame] = {}
    results: list[CompareRow] = []
    total = len(candidates)
    done = 0

    def _get_df(candidate: StrategyCandidate) -> pd.DataFrame:
        cfg = candidate.config
        key = f"{cfg.symbol}_{cfg.timeframe}"
        if key not in data_cache:
            data_cache[key] = load_or_fetch(cfg.symbol, cfg.timeframe, limit=limit, refresh=refresh)
        return data_cache[key]

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_map = {
            pool.submit(_run_one, cand, _get_df(cand)): cand for cand in candidates
        }
        for future in as_completed(future_map):
            cand = future_map[future]
            try:
                row = future.result()
                results.append(row)
                logger.info(
                    f"并行 | {cand.candidate_id} | trades={row.metrics.total_trades} "
                    f"ret={row.metrics.total_return_pct:.2f}% score={row.score:.2f}"
                )
            except Exception as exc:
                logger.error(f"并行失败 {cand.candidate_id}: {exc}")
            done += 1
            if progress:
                progress(done, total)

    return sorted(results, key=lambda r: r.score, reverse=True)


def dedupe_candidates(candidates: list[StrategyCandidate]) -> list[StrategyCandidate]:
    """按策略+参数去重。"""
    seen: set[str] = set()
    unique: list[StrategyCandidate] = []
    for cand in candidates:
        key = config_key(cand.config, cand.strategy)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    return unique
