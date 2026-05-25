"""策略注册表 — 名称、函数、默认参数预设。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from backtest.config import BacktestConfig
from backtest.strategies import adaptive, hybrid, market, momentum, reversion, sentiment_hybrid, sentiment_proxy
from backtest.strategies.base import Signal


@dataclass
class StrategySpec:
    """策略规格。"""

    name: str
    label: str
    fn: Callable
    default_config: BacktestConfig


def _cfg(**overrides) -> BacktestConfig:
    base = BacktestConfig()
    for key, value in overrides.items():
        if hasattr(base, key):
            setattr(base, key, value)
    return base


STRATEGIES: dict[str, StrategySpec] = {
    "market_structure": StrategySpec(
        name="market_structure",
        label="市场结构",
        fn=market.generate_signal,
        default_config=_cfg(timeframe="5m", min_score=85, min_confirmation=3, position_ttl_bars=12),
    ),
    "momentum_breakout": StrategySpec(
        name="momentum_breakout",
        label="动量突破",
        fn=momentum.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            take_profit_pct=0.015,
            stop_loss_pct=0.012,
            position_ttl_bars=15,
            extra={"min_volume_ratio": 1.3},
        ),
    ),
    "hybrid_alpha": StrategySpec(
        name="hybrid_alpha",
        label="混合(结构+动量)",
        fn=hybrid.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            min_score=70,
            min_confirmation=2,
            take_profit_pct=0.018,
            stop_loss_pct=0.012,
            position_ttl_bars=18,
        ),
    ),
    "mean_reversion": StrategySpec(
        name="mean_reversion",
        label="均值回归",
        fn=reversion.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            take_profit_pct=0.012,
            stop_loss_pct=0.008,
            position_ttl_bars=10,
        ),
    ),
    "sentiment_proxy": StrategySpec(
        name="sentiment_proxy",
        label="情绪代理(P5)",
        fn=sentiment_proxy.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            take_profit_pct=0.015,
            stop_loss_pct=0.012,
            position_ttl_bars=20,
            extra={"min_confidence": 70},
        ),
    ),
    "sentiment_hybrid": StrategySpec(
        name="sentiment_hybrid",
        label="情绪+结构(P5)",
        fn=sentiment_hybrid.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            min_score=75,
            min_confirmation=2,
            take_profit_pct=0.014,
            stop_loss_pct=0.011,
            position_ttl_bars=22,
            extra={"min_confidence": 72},
        ),
    ),
    "adaptive_regime": StrategySpec(
        name="adaptive_regime",
        label="自适应(牛/震/熊)",
        fn=adaptive.generate_signal,
        default_config=_cfg(
            timeframe="5m",
            take_profit_pct=0.015,
            stop_loss_pct=0.012,
            position_ttl_bars=20,
            extra={"regime_profiles": None},
        ),
    ),
}


def get_strategy(name: str) -> StrategySpec:
    if name not in STRATEGIES:
        raise KeyError(f"未知策略: {name}，可选: {list(STRATEGIES)}")
    return STRATEGIES[name]


def list_strategies() -> list[str]:
    return list(STRATEGIES.keys())
