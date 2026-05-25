"""策略候选定义 — 策略名 + 参数变体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backtest.config import BacktestConfig


@dataclass
class StrategyCandidate:
    """单次回测候选。"""

    candidate_id: str
    strategy: str
    label: str
    config: BacktestConfig
    generation: int = 0
    parent_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return (
            f"{self.candidate_id} gen={self.generation} "
            f"{self.strategy}/{self.config.timeframe}"
        )
