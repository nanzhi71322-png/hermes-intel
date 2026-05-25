#!/usr/bin/env python3
"""多周期回测对比 + Optuna 优化。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.data_loader import load_or_fetch
from backtest.engine import BacktestEngine
from backtest.optimizer import optuna_search

RESULTS_DIR = ROOT / "data" / "backtest" / "results"


def run_compare(symbol: str, limit: int, refresh: bool) -> list[dict]:
    rows = []
    for timeframe in ("1m", "5m", "15m"):
        cfg = BacktestConfig(symbol=symbol, timeframe=timeframe)
        df = load_or_fetch(symbol, timeframe, limit=limit, refresh=refresh)
        result = BacktestEngine(cfg).run(df=df)
        m = result.metrics
        rows.append(
            {
                "timeframe": timeframe,
                "bars": result.bars,
                "trades": m.total_trades,
                "win_rate": m.win_rate,
                "return_pct": m.total_return_pct,
                "sharpe": m.sharpe_ratio,
                "max_dd": m.max_drawdown_pct,
            }
        )
        print(
            f"{timeframe:>4} | trades={m.total_trades:3d} "
            f"wr={m.win_rate:5.1f}% ret={m.total_return_pct:6.2f}% "
            f"sharpe={m.sharpe_ratio:6.2f} dd={m.max_drawdown_pct:5.2f}%"
        )
    return rows


def run_optimize(symbol: str, timeframe: str, limit: int, trials: int, refresh: bool) -> dict:
    cfg = BacktestConfig(symbol=symbol, timeframe=timeframe)
    df = load_or_fetch(symbol, timeframe, limit=limit, refresh=refresh)
    opt = optuna_search(df, n_trials=trials, base_config=cfg)
    print(f"\n最优参数 ({timeframe}): {opt.best_params}")
    print(f"最优得分: {opt.best_score:.4f}")
    return {"best_params": opt.best_params, "best_score": opt.best_score, "timeframe": timeframe}


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 多周期回测与优化")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--optimize-timeframe", default="5m")
    args = parser.parse_args()

    print("\n========== 多周期对比 ==========")
    compare_rows = run_compare(args.symbol, args.limit, args.refresh)

    print("\n========== Optuna 优化 ==========")
    optimize_result = run_optimize(
        args.symbol,
        args.optimize_timeframe,
        args.limit,
        args.trials,
        args.refresh,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"multi_backtest_{ts}.json"
    payload = {"compare": compare_rows, "optimize": optimize_result}
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
