#!/usr/bin/env python3
"""Hermes 自动回测 CLI — 支持历史回测、走步验证、蒙特卡洛、参数优化。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from backtest.config import BacktestConfig
from backtest.data_loader import load_or_fetch
from backtest.engine import BacktestEngine
from backtest.monte_carlo import monte_carlo_to_dict, run_monte_carlo
from backtest.optimizer import grid_search, optuna_search
from backtest.walk_forward import run_walk_forward, summarize_walk_forward


RESULTS_DIR = ROOT / "data" / "backtest" / "results"


def _print_metrics(metrics) -> None:
    """打印绩效摘要。"""
    print("\n========== 回测绩效 ==========")
    print(f"  总交易数:   {metrics.total_trades}")
    print(f"  胜率:       {metrics.win_rate:.1f}%")
    print(f"  总收益:     {metrics.total_pnl:.4f} USDT ({metrics.total_return_pct:.2f}%)")
    print(f"  盈亏比:     {metrics.payoff_ratio:.2f}")
    print(f"  利润因子:   {metrics.profit_factor:.2f}")
    print(f"  夏普比率:   {metrics.sharpe_ratio:.2f}")
    print(f"  最大回撤:   {metrics.max_drawdown_pct:.2f}%")
    print("================================\n")


def _save_result(name: str, payload: dict) -> Path:
    """保存 JSON 结果。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"{name}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"结果已保存: {path}")
    return path


def cmd_backtest(args: argparse.Namespace) -> None:
    """执行标准历史回测。"""
    cfg = BacktestConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        take_profit_pct=args.tp,
        stop_loss_pct=args.sl,
    )
    engine = BacktestEngine(cfg)
    result = engine.run(limit=args.limit, refresh_data=args.refresh)
    _print_metrics(result.metrics)

    payload = {
        "mode": "backtest",
        "config": cfg.to_dict(),
        "metrics": result.metrics.__dict__,
        "trades_count": len(result.trades),
        "bars": result.bars,
    }
    _save_result("backtest", payload)


def cmd_walkforward(args: argparse.Namespace) -> None:
    """走步验证。"""
    cfg = BacktestConfig(symbol=args.symbol, timeframe=args.timeframe)
    df = load_or_fetch(cfg.symbol, cfg.timeframe, limit=args.limit, refresh=args.refresh)
    folds = run_walk_forward(df, cfg, train_bars=args.train, test_bars=args.test)
    summary = summarize_walk_forward(folds)
    print("\n========== 走步验证 ==========")
    for key, val in summary.items():
        print(f"  {key}: {val}")
    print("================================\n")
    _save_result("walkforward", {"summary": summary, "folds": [f.metrics.__dict__ for f in folds]})


def cmd_montecarlo(args: argparse.Namespace) -> None:
    """蒙特卡洛模拟。"""
    cfg = BacktestConfig(symbol=args.symbol, timeframe=args.timeframe)
    result = BacktestEngine(cfg).run(limit=args.limit, refresh_data=args.refresh)
    pnls = [t["pnl"] for t in result.trades]
    mc = run_monte_carlo(pnls, cfg.starting_balance, simulations=args.sims)
    mc_dict = monte_carlo_to_dict(mc)
    print("\n========== 蒙特卡洛 ==========")
    for key, val in mc_dict.items():
        print(f"  {key}: {val}")
    print("================================\n")
    _save_result("montecarlo", mc_dict)


def cmd_optimize(args: argparse.Namespace) -> None:
    """参数优化。"""
    cfg = BacktestConfig(symbol=args.symbol, timeframe=args.timeframe)
    df = load_or_fetch(cfg.symbol, cfg.timeframe, limit=args.limit, refresh=args.refresh)

    if args.method == "grid":
        grid = {
            "take_profit_pct": [0.008, 0.01, 0.015],
            "stop_loss_pct": [0.008, 0.01, 0.015],
            "min_confirmation": [2, 3],
        }
        opt = grid_search(df, grid, base_config=cfg)
    else:
        opt = optuna_search(df, n_trials=args.trials, base_config=cfg)

    print(f"\n最优参数: {opt.best_params}")
    print(f"最优得分: {opt.best_score:.4f}\n")
    _save_result("optimize", {"best_params": opt.best_params, "best_score": opt.best_score})


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 自动回测系统")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="历史数据回测")
    p_bt.add_argument("--symbol", default="BTC/USDT")
    p_bt.add_argument("--timeframe", default="1m")
    p_bt.add_argument("--limit", type=int, default=5000)
    p_bt.add_argument("--tp", type=float, default=0.01)
    p_bt.add_argument("--sl", type=float, default=0.01)
    p_bt.add_argument("--refresh", action="store_true")
    p_bt.set_defaults(func=cmd_backtest)

    p_wf = sub.add_parser("walkforward", help="走步验证")
    p_wf.add_argument("--symbol", default="BTC/USDT")
    p_wf.add_argument("--timeframe", default="1m")
    p_wf.add_argument("--limit", type=int, default=5000)
    p_wf.add_argument("--train", type=int, default=3000)
    p_wf.add_argument("--test", type=int, default=1000)
    p_wf.add_argument("--refresh", action="store_true")
    p_wf.set_defaults(func=cmd_walkforward)

    p_mc = sub.add_parser("montecarlo", help="蒙特卡洛模拟")
    p_mc.add_argument("--symbol", default="BTC/USDT")
    p_mc.add_argument("--timeframe", default="1m")
    p_mc.add_argument("--limit", type=int, default=5000)
    p_mc.add_argument("--sims", type=int, default=1000)
    p_mc.add_argument("--refresh", action="store_true")
    p_mc.set_defaults(func=cmd_montecarlo)

    p_opt = sub.add_parser("optimize", help="参数优化")
    p_opt.add_argument("--symbol", default="BTC/USDT")
    p_opt.add_argument("--timeframe", default="1m")
    p_opt.add_argument("--limit", type=int, default=5000)
    p_opt.add_argument("--method", choices=["grid", "optuna"], default="optuna")
    p_opt.add_argument("--trials", type=int, default=20)
    p_opt.add_argument("--refresh", action="store_true")
    p_opt.set_defaults(func=cmd_optimize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
