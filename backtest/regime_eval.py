"""分状态回测评估 — 全样本 + 牛/震/熊切片绩效。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtest.config import BacktestConfig
from backtest.indicators import enrich_dataframe
from backtest.metrics import PerformanceMetrics, compute_metrics
from backtest.portfolio import BacktestPortfolio
from backtest.regime import enrich_regime


@dataclass
class RegimeBacktestReport:
    """自适应回测完整报告。"""

    overall: PerformanceMetrics
    by_regime: dict[str, PerformanceMetrics]
    regime_counts: dict[str, int]
    bars: int
    strategy_name: str


def _run_tagged(df: pd.DataFrame, config: BacktestConfig, strategy_fn, strategy_name: str):
    """回测并记录每笔交易入场时的市场状态。"""
    os.environ["HERMES_BACKTEST"] = "1"
    enriched = enrich_regime(enrich_dataframe(df))
    portfolio = BacktestPortfolio(balance=config.starting_balance, max_positions=config.max_open_positions)
    entry_regime: dict[tuple[int, float], str] = {}
    closed_regimes: list[str] = []
    prev_close = None

    for i, row in enriched.iterrows():
        bar_index = int(i)
        price = float(row["close"])
        row_dict = row.to_dict()
        regime = str(row_dict.get("market_regime", "unknown"))
        history = {"prev_close": prev_close}
        before = len(portfolio.closed_trades)

        portfolio.update(
            price=price,
            bar_index=bar_index,
            tp_pct=config.take_profit_pct,
            sl_pct=config.stop_loss_pct,
            ttl_bars=config.position_ttl_bars,
            min_hold_bars=config.min_hold_bars,
            fee_rate=config.fee_rate,
            slippage_pct=config.slippage_pct,
        )

        signal = strategy_fn(row_dict, bar_index, config, history)
        if signal and signal.action in ("long", "short"):
            pos = portfolio.open_position(
                side=signal.action,
                price=signal.price,
                bar_index=bar_index,
                size_pct=config.position_size_pct,
                symbol=config.symbol,
                slippage_pct=config.slippage_pct,
            )
            if pos:
                entry_regime[(pos.entry_bar, pos.entry_price)] = regime

        after = len(portfolio.closed_trades)
        if after > before:
            for trade in portfolio.closed_trades[before:after]:
                key = (trade.entry_bar, trade.entry_price)
                closed_regimes.append(entry_regime.get(key, "unknown"))

        prev_close = price

    return enriched, portfolio, closed_regimes


def metrics_for_regime(
    portfolio: BacktestPortfolio, starting: float, regime: str, regimes: list[str]
) -> PerformanceMetrics:
    """从已平仓交易中筛出特定状态的绩效。"""
    filtered = BacktestPortfolio(balance=starting, max_positions=1)
    for idx, trade in enumerate(portfolio.closed_trades):
        if idx < len(regimes) and regimes[idx] == regime:
            filtered.closed_trades.append(trade)
    return compute_metrics(filtered, starting)


def run_regime_backtest(
    df: pd.DataFrame,
    config: BacktestConfig,
    strategy_fn,
    strategy_name: str = "adaptive_regime",
) -> RegimeBacktestReport:
    """运行自适应策略并输出分状态绩效。"""
    enriched, portfolio, closed_regimes = _run_tagged(df, config, strategy_fn, strategy_name)
    overall = compute_metrics(portfolio, config.starting_balance)
    counts = enriched["market_regime"].value_counts().to_dict()
    by_regime = {
        regime: metrics_for_regime(portfolio, config.starting_balance, regime, closed_regimes)
        for regime in ("bull", "bear", "sideways")
    }
    return RegimeBacktestReport(
        overall=overall,
        by_regime=by_regime,
        regime_counts={str(k): int(v) for k, v in counts.items()},
        bars=len(enriched),
        strategy_name=strategy_name,
    )


def report_to_dict(report: RegimeBacktestReport) -> dict[str, Any]:
    """序列化报告。"""
    return {
        "strategy": report.strategy_name,
        "bars": report.bars,
        "regime_counts": report.regime_counts,
        "overall": report.overall.__dict__,
        "by_regime": {k: v.__dict__ for k, v in report.by_regime.items()},
    }
