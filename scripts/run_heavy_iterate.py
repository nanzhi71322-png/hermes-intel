#!/usr/bin/env python3
"""大规模数据 + 牛/震/熊自适应迭代。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.gate import check_metrics
from backtest.iterate import run_auto_iterate
from backtest.regime_iterate import run_regime_iterate

BEST_FILE = ROOT / "data" / "backtest" / "best_strategy.json"
REGIME_FILE = ROOT / "data" / "backtest" / "regime_best.json"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hermes 大规模自适应迭代")
    parser.add_argument("--days", type=int, default=30, help="历史数据天数")
    parser.add_argument("--regime-gens", type=int, default=15, help="自适应进化代数")
    parser.add_argument("--standard-gens", type=int, default=10, help="常规定策略代数")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--skip-standard", action="store_true")
    args = parser.parse_args()

    limit = args.days * 288
    print(f"\n=== 阶段1: 下载/加载 {args.days} 天 5m 数据 (~{limit} bars) ===")
    best_regime = run_regime_iterate(
        days=args.days,
        generations=args.regime_gens,
        refresh=True,
    )
    _print_regime_summary(best_regime)

    if not args.skip_standard:
        print(f"\n=== 阶段2: 常规定策略并行迭代 ({args.standard_gens} 代) ===")
        run_auto_iterate(
            generations=args.standard_gens,
            variants_per_winner=6,
            top_k=3,
            limit=limit,
            workers=args.workers,
            refresh_every=5,
        )

    print("\n=== 最终晋级检查 ===")
    _check_all_gates()


def _print_regime_summary(result) -> None:
    r = result.report
    print(f"\n自适应最优 代={result.generation} score={result.score:.2f}")
    print(f"  整体: ret={r.overall.total_return_pct:.2f}% wr={r.overall.win_rate:.1f}% trades={r.overall.total_trades}")
    for name, m in r.by_regime.items():
        print(f"  [{name}] ret={m.total_return_pct:.2f}% wr={m.win_rate:.1f}% trades={m.total_trades}")


def _check_all_gates() -> None:
    if REGIME_FILE.exists():
        payload = json.loads(REGIME_FILE.read_text(encoding="utf-8"))
        overall = payload.get("report", {}).get("overall", {})
        g = check_metrics(overall)
        print(f"[regime_adaptive] passed={g.passed} failures={g.failures}")
    if BEST_FILE.exists():
        payload = json.loads(BEST_FILE.read_text(encoding="utf-8"))
        g = check_metrics(payload.get("metrics", {}))
        print(f"[standard_best] strategy={payload.get('strategy')} passed={g.passed}")


if __name__ == "__main__":
    main()
