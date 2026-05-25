"""分市场状态大规模迭代 — 多数据 + 自适应参数进化。"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from backtest.config import BacktestConfig
from backtest.config_utils import clone_config
from backtest.data_loader import load_or_fetch
from backtest.gate import check_metrics
from backtest.metrics import PerformanceMetrics
from backtest.regime import enrich_regime, regime_bar_counts
from backtest.regime_eval import RegimeBacktestReport, report_to_dict, run_regime_backtest
from backtest.regime_profiles import REGIME_PROFILES, mutate_regime_profiles
from backtest.strategies.adaptive import generate_signal as adaptive_signal

ROOT = Path(__file__).resolve().parent.parent
BEST_REGIME_FILE = ROOT / "data" / "backtest" / "regime_best.json"
HISTORY_FILE = ROOT / "data" / "backtest" / "regime_iterate_history.jsonl"


@dataclass
class RegimeIterateResult:
    generation: int
    score: float
    report: RegimeBacktestReport
    profiles: dict[str, Any]


def _score_report(report: RegimeBacktestReport) -> float:
    """综合评分：整体收益 + 分状态均衡（避免只在一种行情里赚）。"""
    o = report.overall
    if o.total_trades < 15:
        return -999.0
    base = o.total_return_pct - o.max_drawdown_pct * 0.4 + o.sharpe_ratio * 1.5
    regime_bonus = 0.0
    for name, m in report.by_regime.items():
        if m.total_trades >= 3:
            regime_bonus += m.total_return_pct * 0.3
    return base + regime_bonus


def _run_one(df, profiles: dict) -> RegimeBacktestReport:
    cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="5m",
        extra={"regime_profiles": profiles},
    )
    return run_regime_backtest(df, cfg, adaptive_signal, "adaptive_regime")


def run_regime_iterate(
    days: int = 30,
    generations: int = 12,
    seed: int = 42,
    refresh: bool = True,
) -> RegimeIterateResult:
    """多代进化 regime_profiles，使用长历史数据。"""
    limit = days * 288
    df = load_or_fetch("BTC/USDT", "5m", limit=limit, refresh=refresh, days=days)
    df = enrich_regime(df)
    counts = regime_bar_counts(df)
    logger.info(f"数据 {len(df)} bars | 状态分布: {counts}")

    rng = random.Random(seed)
    profiles = copy.deepcopy(REGIME_PROFILES)
    best: RegimeIterateResult | None = None

    for gen in range(1, generations + 1):
        report = _run_one(df, profiles)
        score = _score_report(report)
        result = RegimeIterateResult(gen, score, report, copy.deepcopy(profiles))
        logger.info(
            f"代={gen} score={score:.2f} ret={report.overall.total_return_pct:.2f}% "
            f"wr={report.overall.win_rate:.1f}% trades={report.overall.total_trades}"
        )
        _append_history(result)
        if best is None or score > best.score:
            best = result
            _save_best(best, counts)

        if gen >= generations:
            break
        target = rng.choice(["bull", "bear", "sideways"])
        profiles = mutate_regime_profiles(profiles, target, rng)
        if rng.random() < 0.4:
            alt = rng.choice(["bull", "bear", "sideways"])
            profiles = mutate_regime_profiles(profiles, alt, rng)

    assert best is not None
    return best


def _append_history(result: RegimeIterateResult) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "generation": result.generation,
        "score": result.score,
        "profiles": result.profiles,
        "report": report_to_dict(result.report),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _save_best(result: RegimeIterateResult, counts: dict) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "generation": result.generation,
        "score": result.score,
        "regime_counts": counts,
        "profiles": result.profiles,
        "report": report_to_dict(result.report),
        "gate": check_metrics(result.report.overall.__dict__).__dict__,
    }
    BEST_REGIME_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"更新 regime_best score={result.score:.2f}")
