#!/usr/bin/env python3
"""自动迭代 CLI — 并行多策略回测、筛选、进化，可持续循环。"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from backtest.iterate import run_auto_iterate


def _print_summary(summaries) -> None:
    print("\n========== 迭代总结 ==========")
    for item in summaries:
        m = item.best.metrics
        print(
            f"  代={item.generation} 候选={item.candidates} "
            f"最优={item.best.label} ret={m.total_return_pct:.2f}% "
            f"wr={m.win_rate:.1f}% score={item.best.score:.2f}"
        )
    if summaries:
        best = max(summaries, key=lambda s: s.best.score)
        print(f"\n全局最优: 第{best.generation}代 score={best.best.score:.2f}")
    print("=" * 32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 自动迭代引擎")
    parser.add_argument("--generations", type=int, default=5, help="进化代数")
    parser.add_argument("--variants", type=int, default=4, help="每个优胜者变异数")
    parser.add_argument("--top-k", type=int, default=3, help="每代保留优胜者数量")
    parser.add_argument("--limit", type=int, default=5000, help="K线条数")
    parser.add_argument("--workers", type=int, default=6, help="并行 worker 数")
    parser.add_argument("--refresh-every", type=int, default=3, help="每 N 代刷新数据")
    parser.add_argument("--continuous", action="store_true", help="循环运行，不退出")
    parser.add_argument("--sleep-minutes", type=int, default=15, help="连续模式间隔分钟")
    args = parser.parse_args()

    round_idx = 0
    while True:
        round_idx += 1
        started = datetime.now(timezone.utc).isoformat()
        logger.info(f"自动迭代 round={round_idx} start={started}")
        summaries = run_auto_iterate(
            generations=args.generations,
            variants_per_winner=args.variants,
            top_k=args.top_k,
            limit=args.limit,
            workers=args.workers,
            refresh_every=args.refresh_every,
        )
        _print_summary(summaries)
        if not args.continuous:
            break
        logger.info(f"round={round_idx} 完成，{args.sleep_minutes} 分钟后下一轮")
        time.sleep(max(1, args.sleep_minutes) * 60)


if __name__ == "__main__":
    main()
