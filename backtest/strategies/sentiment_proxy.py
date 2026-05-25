"""情绪信号代理策略 — 用 K 线特征模拟 alpha/signal，复现 opportunity_engine。"""

from __future__ import annotations

from typing import Optional

from backtest.config import BacktestConfig
from backtest.strategies.base import Signal
from intel.alpha_engine import compute_alpha, detect_narrative, detect_whale_activity
from intel.opportunity_engine import generate_decision


def _synthetic_text(row: dict) -> str:
    """从行情结构合成伪文本，驱动 signal/alpha 评分。"""
    parts: list[str] = []
    brk = row.get("breakout")
    bias = row.get("market_bias")
    vol = row.get("volume_ratio_1m") or 1.0

    if brk == "up":
        parts.extend(["bullish", "breakout", "inflows", "volume spike"])
    elif brk == "down":
        parts.extend(["bearish", "sell pressure", "liquidation", "outflows"])
    if vol >= 2.0:
        parts.extend(["whale", ">$100m", "large position"])
    if bias == "bullish":
        parts.extend(["etf", "institutional", "accumulation"])
    elif bias == "bearish":
        parts.extend(["macro", "fed", "risk-off"])
    if vol < 1.2:
        parts.extend(["generic", "vague", "sentiment"])
    return " ".join(parts)


def _synthetic_signal_score(row: dict) -> dict:
    """量价激活动态映射 signal_score。"""
    vol = float(row.get("volume_ratio_1m") or 1.0)
    brk = row.get("breakout")
    confirm = int(row.get("confirmation_count", 0) or 0)

    score = 55
    if vol >= 1.5 and brk in ("up", "down"):
        score = 68
    if vol >= 2.0 and confirm >= 2:
        score = 76
    if vol >= 2.5 and brk in ("up", "down") and confirm >= 3:
        score = 82
    return {"score": score}


def generate_signal(
    row: dict, bar_index: int, config: BacktestConfig, history: dict | None = None
) -> Optional[Signal]:
    """复现 live 决策链：合成情绪 → opportunity_engine → 交易信号。"""
    text = _synthetic_text(row)
    signal = _synthetic_signal_score(row)
    whale = detect_whale_activity(text)
    narrative = detect_narrative(text)
    alpha = compute_alpha(signal, whale, narrative)
    price = float(row.get("close", 0) or 0)

    decision = generate_decision(
        signal,
        alpha,
        whale,
        narrative,
        text,
        symbol=config.symbol,
        current_price=price,
    )

    action = decision.get("action")
    if action not in ("long", "short"):
        return None

    min_conf = int(config.extra.get("min_confidence", 70))
    if int(decision.get("confidence", 0) or 0) < min_conf:
        return None

    return Signal(
        action,
        int(decision.get("confidence", 0) or 0),
        decision.get("reason", "sentiment proxy"),
        bar_index,
        price,
    )
