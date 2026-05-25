#!/usr/bin/env python3
"""多策略对比 CLI — 拉最新数据、横向对比、自动调参、输出排名。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.compare import compare_all, rows_to_dict
from backtest.strategies.registry import get_strategy, list_strategies

RESULTS_DIR = ROOT / "data" / "backtest" / "results"


def _print_table(rows) -> None:
    print("\n========== 策略对比排名 ==========")
    print(f"{'排名':<4} {'策略':<18} {'周期':<5} {'交易':<5} {'胜率':<7} {'收益':<8} {'回撤':<7} {'得分':<8} {'调参'}")
    print("-" * 78)
    for idx, row in enumerate(rows, start=1):
        m = row.metrics
        tuned = "是" if row.tuned else "否"
        print(
            f"{idx:<4} {row.label:<18} {row.timeframe:<5} {m.total_trades:<5} "
            f"{m.win_rate:>5.1f}% {m.total_return_pct:>6.2f}% "
            f"{m.max_drawdown_pct:>5.2f}% {row.score:>7.2f} {tuned}"
        )
    print("=" * 78)

    if rows:
        best = rows[0]
        print(f"\n当前最优: {best.label} ({best.strategy})")
        if best.best_params:
            print(f"最优参数: {best.best_params}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 多策略对比与自动调参")
    parser.add_argument("--limit", type=int, default=5000, help="K 线条数")
    parser.add_argument("--refresh", action="store_true", help="强制重新下载数据")
    parser.add_argument("--tune-top", type=int, default=2, help="对排名前 N 策略自动调参")
    parser.add_argument("--trials", type=int, default=15, help="Optuna 试验次数")
    parser.add_argument(
        "--strategies",
        default=",".join(list_strategies()),
        help="逗号分隔策略名",
    )
    args = parser.parse_args()

    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    print(f"对比策略: {names}")
    print(f"数据: limit={args.limit} refresh={args.refresh}")

    rows = compare_all(
        strategy_names=names,
        limit=args.limit,
        refresh=args.refresh,
        auto_tune_top=args.tune_top,
        tune_trials=args.trials,
    )
    _print_table(rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"strategy_compare_{ts}.json"
    payload = {
        "generated_at": ts,
        "limit": args.limit,
        "strategies": names,
        "ranking": rows_to_dict(rows),
    }
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out}")

    if rows:
        best_path = RESULTS_DIR.parent / "best_strategy.json"
        best = rows[0]
        best_payload = {
            "updated_at": ts,
            "strategy": best.strategy,
            "label": best.label,
            "timeframe": best.timeframe,
            "score": best.score,
            "metrics": best.metrics.__dict__,
            "params": best.best_params or {},
            "config": best.metrics and {
                "take_profit_pct": getattr(best, "best_params", {}) or {},
            },
        }
        if best.best_params:
            cfg = get_strategy(best.strategy).default_config
            for key, val in best.best_params.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, val)
            best_payload["applied_config"] = cfg.to_dict()
        with open(best_path, "w", encoding="utf-8") as handle:
            json.dump(best_payload, handle, ensure_ascii=False, indent=2)
        print(f"最优策略配置: {best_path}")


if __name__ == "__main__":
    main()
