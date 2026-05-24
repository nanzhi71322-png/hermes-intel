"""回测配置 — 统一管理策略参数、资金与风控阈值。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacktestConfig:
    """回测运行参数，与 paper_trading 默认值对齐。"""

    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    exchange_id: str = "binance"
    starting_balance: float = 100.0
    position_size_pct: float = 0.10
    max_open_positions: int = 3
    take_profit_pct: float = 0.01
    stop_loss_pct: float = 0.01
    position_ttl_bars: int = 5
    min_hold_bars: int = 1
    fee_rate: float = 0.001
    min_score: int = 85
    min_confirmation: int = 3
    slippage_pct: float = 0.0005
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，便于日志与优化器使用。"""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "starting_balance": self.starting_balance,
            "position_size_pct": self.position_size_pct,
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "position_ttl_bars": self.position_ttl_bars,
            "min_score": self.min_score,
            "min_confirmation": self.min_confirmation,
            "fee_rate": self.fee_rate,
        }
