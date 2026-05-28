"""平仓规则 — 与 paper_trading 对齐。"""
from datetime import datetime

from config.trading import (
    MAX_BTC_PRICE,
    MIN_BTC_PRICE,
    POSITION_MIN_AGE_SECONDS,
    POSITION_TTL_SECONDS,
    TAKE_PROFIT_PCT,
    STOP_LOSS_PCT,
)


def should_close_position(position: dict, current_price: float, now: datetime | None = None) -> dict:
    """返回 {close: bool, reason: str, pnl_pct: float}."""
    now = now or datetime.utcnow()
    entry_price = float(position.get("entry_price", 0))
    position_type = position.get("type", "long")

    if not entry_price or not current_price:
        return {"close": False, "reason": "missing price", "pnl_pct": 0.0}

    if not (MIN_BTC_PRICE <= current_price <= MAX_BTC_PRICE):
        return {"close": False, "reason": "invalid price range", "pnl_pct": 0.0}

    try:
        opened_at = datetime.fromisoformat(position["timestamp"])
    except (TypeError, ValueError, KeyError):
        return {"close": False, "reason": "invalid timestamp", "pnl_pct": 0.0}

    age_seconds = (now - opened_at).total_seconds()
    if age_seconds <= POSITION_MIN_AGE_SECONDS:
        return {"close": False, "reason": "min age not reached", "pnl_pct": 0.0}

    if abs(current_price - entry_price) / entry_price > 0.6:
        return {"close": False, "reason": "abnormal price deviation", "pnl_pct": 0.0}

    if position_type == "short":
        pnl_pct = (entry_price - current_price) / entry_price
    else:
        pnl_pct = (current_price - entry_price) / entry_price

    if abs(pnl_pct) > 0.20:
        return {"close": False, "reason": "invalid pnl jump", "pnl_pct": pnl_pct}

    if pnl_pct >= TAKE_PROFIT_PCT:
        return {"close": True, "reason": "take_profit", "pnl_pct": pnl_pct}

    if pnl_pct <= -STOP_LOSS_PCT:
        return {"close": True, "reason": "stop_loss", "pnl_pct": pnl_pct}

    if age_seconds > POSITION_TTL_SECONDS:
        return {"close": True, "reason": "ttl", "pnl_pct": pnl_pct}

    return {"close": False, "reason": "hold", "pnl_pct": pnl_pct}
