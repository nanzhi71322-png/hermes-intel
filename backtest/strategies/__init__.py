"""策略模块。"""

from backtest.strategies.registry import STRATEGIES, StrategySpec, get_strategy, list_strategies

__all__ = ["STRATEGIES", "StrategySpec", "get_strategy", "list_strategies"]
