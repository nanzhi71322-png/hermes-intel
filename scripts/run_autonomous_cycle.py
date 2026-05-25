#!/usr/bin/env python3
"""自主循环 — 未达标则继续迭代，达标则进入下一步。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from backtest.gate import check_metrics
from backtest.iterate import run_auto_iterate
from backtest.compare import compare_all, rows_to_dict
from backtest.strategies.registry import list_strategies

BEST_FILE = ROOT / "data" / "backtest" / "best_strategy.json"


def _load_best_metrics() -> dict:
    if not BEST_FILE.exists():
        return {}
    payload = json.loads(BEST_FILE.read_text(encoding="utf-8"))
    return payload.get("metrics", {})


def _print_gate(result) -> None:
    if result.passed:
        print("\n[PASS] 回测门槛已通过，进入下一步（同步参数 + 模拟盘验证）")
    else:
        print("\n[FAIL] 未达标，继续迭代:")
        for item in result.failures:
            print(f"   - {item}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hermes 自主晋级循环")
    parser.add_argument("--max-rounds", type=int, default=3, help="最多连续迭代轮数")
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    all_strategies = list_strategies()
    print(f"策略池: {all_strategies}")

    for round_idx in range(1, args.max_rounds + 1):
        print(f"\n{'='*50}\n  第 {round_idx}/{args.max_rounds} 轮自动迭代\n{'='*50}")
        run_auto_iterate(
            generations=args.generations,
            variants_per_winner=5,
            top_k=3,
            limit=args.limit,
            workers=args.workers,
            refresh_every=4 if round_idx == 1 else 0,
        )

        metrics = _load_best_metrics()
        gate = check_metrics(metrics)
        _print_gate(gate)
        if gate.passed:
            _save_next_step_flag()
            return

        print(f"\n--- 扩展策略对比（含 P5 情绪代理）---")
        ranked = compare_all(
            strategy_names=all_strategies,
            limit=args.limit,
            refresh=round_idx == 1,
            auto_tune_top=2,
            tune_trials=12,
        )
        if ranked:
            best = ranked[0]
            m = best.metrics
            print(
                f"对比最优: {best.label} ret={m.total_return_pct:.2f}% "
                f"wr={m.win_rate:.1f}% score={best.score:.2f}"
            )
            gate2 = check_metrics(m.__dict__)
            _print_gate(gate2)
            if gate2.passed:
                _save_next_step_flag()
                return

    print(f"\n完成 {args.max_rounds} 轮仍未达标，可增大 --max-rounds 或 --generations 再跑")


def _save_next_step_flag() -> None:
    flag = ROOT / "data" / "backtest" / "gate_passed.json"
    flag.write_text(
        json.dumps(
            {"passed_at": datetime.now(timezone.utc).isoformat(), "next": "P9_paper_validation"},
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"已标记晋级: {flag}")


if __name__ == "__main__":
    main()
