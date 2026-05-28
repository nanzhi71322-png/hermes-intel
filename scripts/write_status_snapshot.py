#!/usr/bin/env python3
"""写入 data/backtest/status_snapshot.json — 便于查看最近进展。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.gate import check_metrics

BEST = ROOT / "data" / "backtest" / "best_strategy.json"
OUT = ROOT / "data" / "backtest" / "status_snapshot.json"
SCAN_LOG = ROOT / "data" / "backtest" / "deep_scan_history.jsonl"


def main() -> None:
    snap: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}
    if BEST.exists():
        payload = json.loads(BEST.read_text(encoding="utf-8"))
        metrics = payload.get("metrics") or {}
        gate = check_metrics(metrics)
        snap.update(
            {
                "best_strategy": payload.get("strategy"),
                "best_updated_at": payload.get("updated_at"),
                "metrics": metrics,
                "gate_passed": gate.passed,
                "gate_failures": gate.failures,
            }
        )
    if SCAN_LOG.exists():
        lines = [ln for ln in SCAN_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            snap["last_deep_scan"] = json.loads(lines[-1])
    OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
