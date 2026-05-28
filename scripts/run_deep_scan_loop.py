#!/usr/bin/env python3
"""每 N 小时深度扫描：刷新数据 → 自适应迭代 → gate 检查 → 记录。"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from backtest.gate import check_metrics
from backtest.iterate import run_auto_iterate
from backtest.regime_iterate import run_regime_iterate

BEST_FILE = ROOT / "data" / "backtest" / "best_strategy.json"
LOG_FILE = ROOT / "data" / "backtest" / "deep_scan_history.jsonl"


def _record(scan: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(scan, ensure_ascii=False) + "\n")


def _deep_scan_once(days: int, regime_gens: int, standard_gens: int, workers: int) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    limit = days * 288
    logger.info(f"深度扫描开始 days={days} limit={limit}")

    regime = run_regime_iterate(days=days, generations=regime_gens, refresh=True)
    summaries = run_auto_iterate(
        generations=standard_gens,
        variants_per_winner=5,
        top_k=3,
        limit=limit,
        workers=workers,
        refresh_every=0,
    )

    metrics = {}
    gate_payload = {"passed": False, "failures": ["no best_strategy.json"]}
    if BEST_FILE.exists():
        payload = json.loads(BEST_FILE.read_text(encoding="utf-8"))
        metrics = payload.get("metrics") or {}
        gate_payload = check_metrics(metrics).__dict__

    best_gen = summaries[-1].best if summaries else None
    scan = {
        "timestamp": ts,
        "days": days,
        "regime_score": regime.score,
        "regime_return_pct": regime.report.overall.total_return_pct,
        "best_label": best_gen.label if best_gen else None,
        "best_return_pct": metrics.get("total_return_pct"),
        "best_win_rate": metrics.get("win_rate"),
        "gate_passed": gate_payload.get("passed"),
        "gate_failures": gate_payload.get("failures"),
    }
    _record(scan)
    return scan


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hermes 定时深度扫描")
    parser.add_argument("--sleep-minutes", type=int, default=120, help="扫描间隔（默认 2 小时）")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--regime-gens", type=int, default=8)
    parser.add_argument("--standard-gens", type=int, default=6)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--once", action="store_true", help="只跑一轮后退出")
    args = parser.parse_args()

    round_idx = 0
    while True:
        round_idx += 1
        try:
            scan = _deep_scan_once(args.days, args.regime_gens, args.standard_gens, args.workers)
            status = "PASS" if scan["gate_passed"] else "FAIL"
            logger.info(
                f"深度扫描 #{round_idx} [{status}] ret={scan.get('best_return_pct')}% "
                f"wr={scan.get('best_win_rate')}% failures={scan.get('gate_failures')}"
            )
            if scan["gate_passed"]:
                logger.info("门槛已通过，可执行 P7/P9：同步 best_strategy 到模拟盘并做 7 天验证")
                return
        except Exception as exc:
            logger.exception(f"深度扫描 #{round_idx} 异常: {exc}")
            _record({"timestamp": datetime.now(timezone.utc).isoformat(), "error": str(exc)})

        if args.once:
            break
        logger.info(f"{args.sleep_minutes} 分钟后下一轮深度扫描")
        time.sleep(max(1, args.sleep_minutes) * 60)


if __name__ == "__main__":
    main()
