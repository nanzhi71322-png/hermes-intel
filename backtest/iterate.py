"""自动迭代引擎 — 多轮并行筛选 + 进化。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from backtest.candidate import StrategyCandidate
from backtest.compare import CompareRow, rows_to_dict
from backtest.config_utils import clone_config
from backtest.evolve import build_seed_pool, evolve_next_generation
from backtest.parallel_runner import dedupe_candidates, run_parallel
from backtest.gate import check_metrics, is_better_candidate, iteration_score, metrics_from_any
from backtest.strategies.registry import get_strategy

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "data" / "backtest" / "iterate_history.jsonl"
BEST_FILE = ROOT / "data" / "backtest" / "best_strategy.json"
RESULTS_DIR = ROOT / "data" / "backtest" / "results"


@dataclass
class IterateSummary:
    """一轮迭代摘要。"""

    generation: int
    candidates: int
    best: CompareRow
    top5: list[CompareRow]


def _load_best_params() -> StrategyCandidate | None:
    if not BEST_FILE.exists():
        return None
    try:
        payload = json.loads(BEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    strategy = payload.get("strategy")
    if not strategy:
        return None
    spec = get_strategy(strategy)
    cfg = clone_config(spec.default_config)
    for key, val in (payload.get("params") or {}).items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    for key, val in (payload.get("applied_config") or {}).items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return StrategyCandidate(
        candidate_id="prev-best",
        strategy=strategy,
        label=payload.get("label", spec.label),
        config=cfg,
        generation=-1,
        params=payload.get("params") or {},
    )


def _row_strategy_name(row: CompareRow) -> str:
    label = row.strategy
    return label.split("[")[0] if "[" in label else label


def _winner_to_candidate(row: CompareRow, generation: int, idx: int) -> StrategyCandidate:
    name = _row_strategy_name(row)
    spec = get_strategy(name)
    cfg = clone_config(spec.default_config, timeframe=row.timeframe)
    params = dict(row.best_params or {})
    for key, val in params.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return StrategyCandidate(
        candidate_id=f"win-g{generation}-{idx}",
        strategy=name,
        label=spec.label,
        config=cfg,
        generation=generation,
        params=params,
    )


def save_generation(summary: IterateSummary) -> None:
    """持久化本代结果，刷新历史最优。"""
    ts = datetime.now(timezone.utc).isoformat()
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": ts,
        "generation": summary.generation,
        "candidates": summary.candidates,
        "best": rows_to_dict([summary.best])[0],
        "top5": rows_to_dict(summary.top5),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"iterate_gen{summary.generation}_{stamp}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    best_row = summary.best
    best_name = _row_strategy_name(best_row)
    spec = get_strategy(best_name)
    cfg = clone_config(spec.default_config, timeframe=best_row.timeframe)
    params = dict(best_row.best_params or {})
    for key, val in params.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)

    old_payload = None
    if BEST_FILE.exists():
        try:
            old_payload = json.loads(BEST_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old_payload = None

    metrics_dict = metrics_from_any(best_row.metrics)
    iter_score = iteration_score(metrics_dict)
    if is_better_candidate(best_row.metrics, iter_score, old_payload):
        gate = check_metrics(metrics_dict)
        payload = {
            "updated_at": ts,
            "generation": summary.generation,
            "strategy": best_name,
            "label": spec.label,
            "timeframe": best_row.timeframe,
            "score": best_row.score,
            "iteration_score": iter_score,
            "gate_passed": gate.passed,
            "gate_failures": gate.failures,
            "params": params,
            "applied_config": cfg.to_dict(),
            "metrics": metrics_dict,
        }
        BEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"更新最优策略 iter_score={iter_score:.2f} gate={gate.passed}")


def run_auto_iterate(
    generations: int = 5,
    variants_per_winner: int = 4,
    top_k: int = 3,
    limit: int = 5000,
    workers: int = 6,
    refresh_every: int = 3,
    seed: int = 42,
) -> list[IterateSummary]:
    """多代自动迭代：并行跑批 → 筛选 → 变异 → 再跑。"""
    summaries: list[IterateSummary] = []
    pool = build_seed_pool(seed)
    prev_best = _load_best_params()
    if prev_best:
        pool.insert(0, prev_best)

    for gen in range(1, generations + 1):
        refresh = gen == 1 or (refresh_every > 0 and gen % refresh_every == 0)
        pool = dedupe_candidates(pool)
        logger.info(f"===== 第 {gen}/{generations} 代 | 候选={len(pool)} =====")
        ranked = run_parallel(pool, limit=limit, refresh=refresh, workers=workers)
        summary = IterateSummary(generation=gen, candidates=len(pool), best=ranked[0], top5=ranked[:5])
        summaries.append(summary)
        save_generation(summary)

        if gen >= generations:
            break
        winners = [_winner_to_candidate(row, gen, i) for i, row in enumerate(ranked[:top_k])]
        pool = winners + evolve_next_generation(winners, gen + 1, variants_per_winner, seed)

    return summaries
