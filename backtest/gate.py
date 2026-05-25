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
