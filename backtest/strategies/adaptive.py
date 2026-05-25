"""自适应策略 — 根据牛/震/熊切换子策略与参数。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.regime_profiles import REGIME_PROFILES, config_for_regime
from backtest.strategies.base import Signal


def _side_allowed(action: str, prefer: str) -> bool:
    if prefer in ("both", "", None):
        return True
    if prefer == "long":
        return action == "long"
    if prefer == "short":
        return action == "short"
    return True


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """读取 market_regime，路由到对应子策略。"""
    regime = row.get("market_regime", "unknown")
    if regime == "unknown":
        return None

    profiles = config.extra.get("regime_profiles") or REGIME_PROFILES
    profile = profiles.get(regime, profiles.get("unknown", REGIME_PROFILES["unknown"]))
    strategy_name = profile.get("strategy", "sentiment_hybrid")
    from backtest.strategies.registry import get_strategy

    spec = get_strategy(strategy_name)

    cfg = config_for_regime(config, regime)
    if config.extra.get("regime_profiles"):
        params = profile.get("params", {})
        for key, val in params.items():
            if key == "extra" and isinstance(val, dict):
                cfg.extra.update(val)
            elif hasattr(cfg, key):
                setattr(cfg, key, val)

    signal = spec.fn(row, bar_index, cfg, history)
    if not signal:
        return None

    prefer = cfg.extra.get("prefer_side", "both")
    if not _side_allowed(signal.action, prefer):
        return None

    return Signal(
        signal.action,
        signal.confidence,
        f"[{regime}] {signal.reason}",
        bar_index,
        signal.price,
    )
