"""回测配置克隆工具。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backtest.config import BacktestConfig


def clone_config(base: BacktestConfig, **overrides: Any) -> BacktestConfig:
    """深拷贝配置并覆盖字段。"""
    cfg = deepcopy(base)
    for key, value in overrides.items():
        if key == "extra" and isinstance(value, dict):
            cfg.extra = {**cfg.extra, **value}
        elif hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg


def config_key(cfg: BacktestConfig, strategy: str) -> str:
    """生成候选唯一键，用于去重。"""
    parts = [
        strategy,
        cfg.timeframe,
        f"tp{cfg.take_profit_pct:.4f}",
        f"sl{cfg.stop_loss_pct:.4f}",
        f"ttl{cfg.position_ttl_bars}",
        f"ms{cfg.min_score}",
        f"mc{cfg.min_confirmation}",
    ]
    if cfg.extra:
        for key in sorted(cfg.extra.keys()):
            parts.append(f"{key}={cfg.extra[key]}")
    return "|".join(parts)
