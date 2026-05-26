#!/usr/bin/env python3
"""针对晋级门槛的 Optuna 精调 — 在 30 天数据上搜索可过 gate 的参数。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config_utils import clone_config
from backtest.data_loader import load_or_fetch
from backtest.engine import BacktestEngine
from backtest.gate import check_metrics, iteration_score, metrics_from_any
from backtest.strategies.registry import STRATEGIES, get_strategy

BEST_FILE = ROOT / "data" / "backtest" / "best_strategy.json"

TARGETS = (
    "sentiment_hybrid",
    "hybrid_alpha",
    "sentiment_proxy",
    "mean_reversion",
    "momentum_breakout",
)


def _optuna_one(df, name: str, trials: int) -> dict | None:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    spec = get_strategy(name)
    best_gate = None

    def objective(trial: optuna.Trial) -> float:
        params = {
            "take_profit_pct": trial.suggest_float("take_profit_pct", 0.006, 0.035),
            "stop_loss_pct": trial.suggest_float("stop_loss_pct", 0.005, 0.025),
            "position_ttl_bars": trial.suggest_int("position_ttl_bars", 6, 36),
            "min_score": trial.suggest_int("min_score", 65, 88),
            "min_confirmation": trial.suggest_int("min_confirmation", 2, 4),
        }
        extra = dict(spec.default_config.extra or {})
        if name in ("sentiment_proxy", "sentiment_hybrid"):
            extra["min_confidence"] = trial.suggest_int("min_confidence", 65, 85)
        if name == "sentiment_hybrid":
            extra["dual_mode"] = trial.suggest_categorical("dual_mode", ["strict", "soft"])
            extra["soft_min_confidence"] = trial.suggest_int("soft_min_confidence", 72, 90)
        cfg = clone_config(spec.default_config, timeframe="5m", extra=extra, **params)
        result = BacktestEngine(cfg, spec.fn, name).run(df=df)
        m = metrics_from_any(result.metrics)
        gate = check_metrics(m)
        nonlocal best_gate
        if gate.passed and (best_gate is None or m["total_return_pct"] > best_gate["total_return_pct"]):
            best_gate = {**m, "params": params, "extra": extra}
        return iteration_score(m)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=trials)
    if not best_gate:
        return None
    return {
        "strategy": name,
        "label": spec.label,
        "params": best_gate.pop("params"),
        "extra": best_gate.pop("extra", {}),
        "metrics": {k: v for k, v in best_gate.items()},
        "optuna_best": study.best_params,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--trials", type=int, default=35, help="每策略 Optuna 次数")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    limit = args.days * 288
    df = load_or_fetch("BTC/USDT", "5m", limit=limit, refresh=args.refresh, days=args.days)
    print(f"数据 bars={len(df)}")

    winners: list[dict] = []
    for name in TARGETS:
        print(f"\n--- Optuna {name} ({args.trials} trials) ---")
        hit = _optuna_one(df, name, args.trials)
        if hit:
            g = check_metrics(hit["metrics"])
            print(f"[GATE PASS] {name} ret={hit['metrics']['total_return_pct']:.3f}% wr={hit['metrics']['win_rate']:.1f}%")
            winners.append(hit)
        else:
            print(f"[no pass] {name}")

    if not winners:
        print("\n本轮未找到过 gate 的组合，继续 run_heavy_iterate / run_autonomous_cycle")
        return

    best = max(winners, key=lambda w: w["metrics"]["total_return_pct"])
    spec = get_strategy(best["strategy"])
    cfg = clone_config(spec.default_config, timeframe="5m", extra=best.get("extra") or {})
    for k, v in best["params"].items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    payload = {
        "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "generation": 0,
        "strategy": best["strategy"],
        "label": best["label"],
        "timeframe": "5m",
        "score": iteration_score(best["metrics"]),
        "iteration_score": iteration_score(best["metrics"]),
        "gate_passed": True,
        "gate_failures": [],
        "params": best["params"],
        "applied_config": cfg.to_dict(),
        "metrics": best["metrics"],
        "source": "run_gate_optimize",
    }
    BEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {BEST_FILE.name}: {best['strategy']} ret={best['metrics']['total_return_pct']:.3f}%")


if __name__ == "__main__":
    main()
