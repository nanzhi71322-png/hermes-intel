"""分市场状态策略配置 — 牛/震/熊各用不同逻辑。"""

from __future__ import annotations

from typing import Any

from backtest.config import BacktestConfig
from backtest.config_utils import clone_config

# 各状态默认：策略名 + 参数微调方向
REGIME_PROFILES: dict[str, dict[str, Any]] = {
    "bull": {
        "strategy": "momentum_breakout",
        "params": {
            "take_profit_pct": 0.022,
            "stop_loss_pct": 0.011,
            "position_ttl_bars": 24,
            "min_score": 70,
            "min_confirmation": 2,
            "extra": {"min_volume_ratio": 1.2, "prefer_side": "long"},
        },
    },
    "bear": {
        "strategy": "sentiment_hybrid",
        "params": {
            "take_profit_pct": 0.018,
            "stop_loss_pct": 0.014,
            "position_ttl_bars": 18,
            "min_score": 75,
            "min_confirmation": 2,
            "extra": {"min_confidence": 72, "prefer_side": "short"},
        },
    },
    "sideways": {
        "strategy": "mean_reversion",
        "params": {
            "take_profit_pct": 0.010,
            "stop_loss_pct": 0.008,
            "position_ttl_bars": 12,
            "min_score": 70,
            "min_confirmation": 2,
            "extra": {"prefer_side": "both"},
        },
    },
    "unknown": {
        "strategy": "sentiment_hybrid",
        "params": {
            "take_profit_pct": 0.014,
            "stop_loss_pct": 0.012,
            "position_ttl_bars": 20,
        },
    },
}


def config_for_regime(base: BacktestConfig, regime: str) -> BacktestConfig:
    """按市场状态生成回测配置。"""
    profile = REGIME_PROFILES.get(regime, REGIME_PROFILES["unknown"])
    params = dict(profile.get("params", {}))
    extra = {**base.extra, **params.pop("extra", {})}
    cfg = clone_config(base, extra=extra, **params)
    cfg.extra["regime"] = regime
    cfg.extra["regime_strategy"] = profile["strategy"]
    return cfg


def mutate_regime_profiles(
    profiles: dict[str, dict[str, Any]],
    regime: str,
    rng,
) -> dict[str, dict[str, Any]]:
    """对单一状态的参数做小幅变异。"""
    import copy

    out = copy.deepcopy(profiles)
    p = out.get(regime, REGIME_PROFILES.get(regime, {}))
    params = p.setdefault("params", {})
    params["take_profit_pct"] = max(
        0.005,
        min(0.04, params.get("take_profit_pct", 0.015) * rng.uniform(0.85, 1.15)),
    )
    params["stop_loss_pct"] = max(
        0.005,
        min(0.04, params.get("stop_loss_pct", 0.012) * rng.uniform(0.85, 1.15)),
    )
    params["position_ttl_bars"] = max(
        5,
        min(40, int(params.get("position_ttl_bars", 18) + rng.choice([-3, 0, 3]))),
    )
    return out
