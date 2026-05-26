"""策略进化 — 从优胜者变异出下一代候选。"""

from __future__ import annotations

import random
from typing import Any

from backtest.candidate import StrategyCandidate
from backtest.config_utils import clone_config
from backtest.strategies.registry import STRATEGIES, get_strategy


def _mutate_float(value: float, low: float, high: float, scale: float, rng: random.Random) -> float:
    factor = rng.uniform(1 - scale, 1 + scale)
    return max(low, min(high, value * factor))


def _mutate_int(value: int, low: int, high: int, step: int, rng: random.Random) -> int:
    delta = rng.choice([-step, 0, step])
    return max(low, min(high, value + delta))


def mutate_candidate(
    parent: StrategyCandidate,
    generation: int,
    variant_idx: int,
    rng: random.Random | None = None,
) -> StrategyCandidate:
    """围绕父代参数做小幅随机变异。"""
    rng = rng or random.Random()
    base = parent.config
    params: dict[str, Any] = {
        "take_profit_pct": _mutate_float(base.take_profit_pct, 0.005, 0.04, 0.15, rng),
        "stop_loss_pct": _mutate_float(base.stop_loss_pct, 0.005, 0.04, 0.15, rng),
        "position_ttl_bars": _mutate_int(base.position_ttl_bars, 3, 40, 3, rng),
        "min_score": _mutate_int(base.min_score, 65, 90, 3, rng),
        "min_confirmation": _mutate_int(base.min_confirmation, 2, 4, 1, rng),
    }
    extra_overrides: dict[str, Any] = {}
    if parent.strategy in ("sentiment_hybrid", "sentiment_proxy"):
        extra = dict(parent.config.extra or {})
        extra["min_confidence"] = _mutate_int(
            int(extra.get("min_confidence", 70)), 65, 88, 3, rng
        )
        if parent.strategy == "sentiment_hybrid":
            extra["dual_mode"] = rng.choice(["strict", "soft", "soft"])
            extra["soft_min_confidence"] = _mutate_int(
                int(extra.get("soft_min_confidence", 78)), 72, 92, 2, rng
            )
        extra_overrides = extra

    if extra_overrides:
        cfg = clone_config(base, **params, extra=extra_overrides)
        params = {**params, "extra": extra_overrides}
    else:
        cfg = clone_config(base, **params)
    cid = f"g{generation}-v{variant_idx}-{parent.strategy[:4]}"
    return StrategyCandidate(
        candidate_id=cid,
        strategy=parent.strategy,
        label=get_strategy(parent.strategy).label,
        config=cfg,
        generation=generation,
        parent_id=parent.candidate_id,
        params=params,
    )


def build_seed_pool(seed: int = 42) -> list[StrategyCandidate]:
    """初始候选池：4 策略 × 多周期 × 参数预设。"""
    rng = random.Random(seed)
    seeds: list[StrategyCandidate] = []
    timeframes = ("1m", "5m", "15m")
    idx = 0

    for name, spec in STRATEGIES.items():
        for tf in timeframes:
            ttl = {"1m": 8, "5m": 15, "15m": 6}[tf]
            tp = {"1m": 0.012, "5m": 0.018, "15m": 0.025}[tf]
            cfg = clone_config(spec.default_config, timeframe=tf, position_ttl_bars=ttl, take_profit_pct=tp)
            seeds.append(
                StrategyCandidate(
                    candidate_id=f"seed-{idx}",
                    strategy=name,
                    label=spec.label,
                    config=cfg,
                    generation=0,
                )
            )
            idx += 1

        for _ in range(2):
            parent = StrategyCandidate(
                candidate_id=f"seed-{idx}",
                strategy=name,
                label=spec.label,
                config=clone_config(spec.default_config),
                generation=0,
            )
            seeds.append(mutate_candidate(parent, 0, idx, rng))
            idx += 1

    return seeds


def evolve_next_generation(
    winners: list[StrategyCandidate],
    generation: int,
    variants_per_winner: int = 4,
    seed: int = 42,
) -> list[StrategyCandidate]:
    """从优胜者生成下一代变异候选。"""
    rng = random.Random(seed + generation)
    children: list[StrategyCandidate] = []
    for winner in winners:
        for i in range(variants_per_winner):
            children.append(mutate_candidate(winner, generation, i, rng))
    return children
