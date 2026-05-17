from datetime import datetime

from loguru import logger


MAX_PENDING_CANDIDATES = 200
pending_candidates = []


def _parse_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp

    return datetime.fromisoformat(timestamp)


def record_market_candidate(
    timestamp,
    symbol,
    market_price,
    market_candidate,
    market_state,
    decision,
):
    if market_candidate.get("action") not in ("long", "short"):
        return

    if market_price is None:
        return

    candidate = {
        "timestamp": timestamp,
        "symbol": symbol,
        "entry_price": float(market_price),
        "action": market_candidate.get("action"),
        "confidence": market_candidate.get("confidence"),
        "reason": market_candidate.get("reason"),
        "market_bias": market_state.get("market_bias"),
        "market_score": market_state.get("score"),
        "confirmation_count": market_state.get("confirmation_count"),
        "bullish_count": market_state.get("bullish_count"),
        "bearish_count": market_state.get("bearish_count"),
        "bullish_reasons": market_state.get("bullish_reasons"),
        "bearish_reasons": market_state.get("bearish_reasons"),
        "decision_action": decision.get("action") if decision else None,
        "decision_confidence": decision.get("confidence") if decision else None,
        "evaluated_60s": False,
        "evaluated_180s": False,
        "evaluated_300s": False,
    }

    pending_candidates.append(candidate)

    if len(pending_candidates) > MAX_PENDING_CANDIDATES:
        del pending_candidates[:len(pending_candidates) - MAX_PENDING_CANDIDATES]


def _build_event(candidate, current_price, horizon):
    entry_price = candidate["entry_price"]
    action = candidate["action"]

    if action == "long":
        pnl_pct = (current_price - entry_price) / entry_price
    else:
        pnl_pct = (entry_price - current_price) / entry_price

    event = {
        "horizon": horizon,
        "symbol": candidate["symbol"],
        "action": action,
        "entry_price": entry_price,
        "current_price": current_price,
        "pnl_pct": pnl_pct,
        "win": pnl_pct > 0,
        "confidence": candidate["confidence"],
        "market_bias": candidate["market_bias"],
        "market_score": candidate["market_score"],
        "reason": candidate["reason"],
    }
    logger.info(
        f"[market candidate tracker] horizon={horizon} "
        f"action={action} pnl_pct={pnl_pct:.6f}"
    )
    return event


def evaluate_market_candidates(current_timestamp, symbol, current_price):
    if current_price is None:
        return []

    now = _parse_timestamp(current_timestamp)
    current_price = float(current_price)
    events = []
    remaining_candidates = []

    for candidate in pending_candidates:
        if candidate["symbol"] != symbol:
            remaining_candidates.append(candidate)
            continue

        try:
            started_at = _parse_timestamp(candidate["timestamp"])
        except (TypeError, ValueError):
            continue

        elapsed_seconds = (now - started_at).total_seconds()

        if elapsed_seconds >= 60 and not candidate["evaluated_60s"]:
            events.append(_build_event(candidate, current_price, "60s"))
            candidate["evaluated_60s"] = True

        if elapsed_seconds >= 180 and not candidate["evaluated_180s"]:
            events.append(_build_event(candidate, current_price, "180s"))
            candidate["evaluated_180s"] = True

        if elapsed_seconds >= 300 and not candidate["evaluated_300s"]:
            events.append(_build_event(candidate, current_price, "300s"))
            candidate["evaluated_300s"] = True
            continue

        remaining_candidates.append(candidate)

    pending_candidates[:] = remaining_candidates

    return events
