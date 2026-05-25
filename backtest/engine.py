"""回测引擎 — 支持多策略注入与历史上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import pandas as pd
from loguru import logger

from backtest.config import BacktestConfig
from backtest.data_loader import load_or_fetch
from backtest.indicators import enrich_dataframe
from backtest.market_strategy import generate_signal as default_signal
from backtest.metrics import PerformanceMetrics, compute_metrics
from backtest.portfolio import BacktestPortfolio


@dataclass
class BacktestResult:
    """回测完整输出。"""

    metrics: PerformanceMetrics
    trades: list[dict[str, Any]]
    equity_curve: list[float]
    config: BacktestConfig
    bars: int
    strategy_name: str = "market_structure"


class BacktestEngine:
    """主回测执行器。"""

    def __init__(
        self,
        config: BacktestConfig | None = None,
        strategy_fn: Callable | None = None,
        strategy_name: str = "market_structure",
    ) -> None:
        self.config = config or BacktestConfig()
        self.strategy_fn = strategy_fn or default_signal
        self.strategy_name = strategy_name

    def run(
        self,
        df: pd.DataFrame | None = None,
        limit: int = 5000,
        refresh_data: bool = False,
    ) -> BacktestResult:
        """执行一次完整回测。"""
        cfg = self.config
        if df is None:
            df = load_or_fetch(
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                limit=limit,
                exchange_id=cfg.exchange_id,
                refresh=refresh_data,
            )

        enriched = enrich_dataframe(df)
        portfolio = BacktestPortfolio(balance=cfg.starting_balance, max_positions=cfg.max_open_positions)
        prev_close: Optional[float] = None

        for i, row in enriched.iterrows():
            bar_index = int(i)
            price = float(row["close"])
            row_dict = row.to_dict()
            history = {"prev_close": prev_close}

            portfolio.update(
                price=price,
                bar_index=bar_index,
                tp_pct=cfg.take_profit_pct,
                sl_pct=cfg.stop_loss_pct,
                ttl_bars=cfg.position_ttl_bars,
                min_hold_bars=cfg.min_hold_bars,
                fee_rate=cfg.fee_rate,
                slippage_pct=cfg.slippage_pct,
            )

            signal = self.strategy_fn(row_dict, bar_index, cfg, history)
            if signal and signal.action in ("long", "short"):
                portfolio.open_position(
                    side=signal.action,
                    price=signal.price,
                    bar_index=bar_index,
                    size_pct=cfg.position_size_pct,
                    symbol=cfg.symbol,
                    slippage_pct=cfg.slippage_pct,
                )

            prev_close = price

        metrics = compute_metrics(portfolio, cfg.starting_balance)
        trades = [
            {
                "side": t.side,
                "pnl": round(t.pnl, 4),
                "pnl_pct": round(t.pnl_pct * 100, 3),
                "reason": t.reason,
                "entry_bar": t.entry_bar,
                "exit_bar": t.exit_bar,
            }
            for t in portfolio.closed_trades
        ]

        logger.info(
            f"[{self.strategy_name}] 回测完成 | 交易={metrics.total_trades} "
            f"胜率={metrics.win_rate:.1f}% 总PnL={metrics.total_pnl:.2f} "
            f"夏普={metrics.sharpe_ratio:.2f} 最大回撤={metrics.max_drawdown_pct:.2f}%"
        )

        return BacktestResult(
            metrics=metrics,
            trades=trades,
            equity_curve=portfolio.equity_curve,
            config=cfg,
            bars=len(enriched),
            strategy_name=self.strategy_name,
        )
