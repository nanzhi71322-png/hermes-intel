"""回测晋级门槛 — 达标进下一步，未达标继续迭代。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GateResult:
    """门槛检查结果。"""

    passed: bool
    failures: list[str]
    metrics: dict[str, Any]


def check_metrics(metrics: dict[str, Any]) -> GateResult:
    """检查是否达到进入模拟盘验证的最低回测标准。"""
    failures: list[str] = []
    trades = int(metrics.get("total_trades", 0) or 0)
    ret = float(metrics.get("total_return_pct", 0) or 0)
    wr = float(metrics.get("win_rate", 0) or 0)
    dd = float(metrics.get("max_drawdown_pct", 100) or 100)
    sharpe = float(metrics.get("sharpe_ratio", 0) or 0)
    payoff = float(metrics.get("payoff_ratio", 0) or 0)
    pf = float(metrics.get("profit_factor", 0) or 0)

    if trades < 10:
        failures.append(f"交易数不足({trades}<10)")
    if ret <= 0:
        failures.append(f"收益未转正({ret:.2f}%)")
    if wr < 45:
        failures.append(f"胜率不足({wr:.1f}%<45%)")
    if dd >= 15:
        failures.append(f"回撤过大({dd:.2f}%>=15%)")
    if sharpe < 0.3:
        failures.append(f"夏普不足({sharpe:.2f}<0.3)")
    if payoff < 1.0 and pf < 1.0:
        failures.append(f"盈亏比/利润因子不足(payoff={payoff:.2f}, pf={pf:.2f})")

    return GateResult(passed=len(failures) == 0, failures=failures, metrics=metrics)


def metrics_from_any(metrics: Any) -> dict[str, Any]:
    """PerformanceMetrics 或 dict → 统一 dict。"""
    if hasattr(metrics, "__dict__") and not isinstance(metrics, dict):
        return dict(metrics.__dict__)
    return dict(metrics or {})


def iteration_score(metrics: Any) -> float:
    """迭代用评分 — 与 gate 对齐，达标候选大幅加分。"""
    m = metrics_from_any(metrics)
    gate = check_metrics(m)
    if gate.passed:
        return 1000.0 + float(m.get("total_return_pct", 0) or 0) * 10 + float(m.get("sharpe_ratio", 0) or 0) * 5

    score = float(m.get("total_return_pct", 0) or 0)
    score -= float(m.get("max_drawdown_pct", 0) or 0) * 0.5
    score += float(m.get("sharpe_ratio", 0) or 0) * 2.0
    score += (float(m.get("win_rate", 0) or 0) - 45.0) * 0.15

    trades = int(m.get("total_trades", 0) or 0)
    if trades < 10:
        score -= 50.0
    for msg in gate.failures:
        if "收益未转正" in msg:
            score -= max(2.0, abs(float(m.get("total_return_pct", 0) or 0)) * 5)
        elif "胜率不足" in msg:
            score -= (45.0 - float(m.get("win_rate", 0) or 0)) * 0.5
        elif "夏普不足" in msg:
            score -= 3.0
        elif "利润因子" in msg or "盈亏比" in msg:
            score -= 2.0
        elif "回撤过大" in msg:
            score -= 10.0
        else:
            score -= 1.0
    return score


def is_better_candidate(new_metrics: Any, new_score: float, old_payload: dict | None) -> bool:
    """保存最优时：已达标优先，否则比 iteration_score。"""
    new_gate = check_metrics(metrics_from_any(new_metrics))
    if not old_payload:
        return True
    old_gate = check_metrics(old_payload.get("metrics") or {})
    if new_gate.passed and not old_gate.passed:
        return True
    if old_gate.passed and not new_gate.passed:
        return False
    old_m = old_payload.get("metrics") or {}
    old_iter = iteration_score(old_m)
    new_iter = iteration_score(new_metrics)
    if abs(old_iter - new_iter) < 1e-6:
        return float(new_m.get("total_return_pct", 0) or 0) > float(old_m.get("total_return_pct", 0) or 0)
    return new_iter > old_iter
