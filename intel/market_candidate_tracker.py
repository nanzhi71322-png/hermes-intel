from datetime import datetime
from copy import deepcopy

from loguru import logger


MAX_PENDING_CANDIDATES = 200
pending_candidates = []
last_recorded_candidates = {}
candidate_stats = {
    "60s": {},
    "180s": {},
    "300s": {},
}


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

    action = market_candidate.get("action")
    duplicate_key = (symbol, action)
    try:
        recorded_at = _parse_timestamp(timestamp)
        last_recorded_at = last_recorded_candidates.get(duplicate_key)
        if last_recorded_at and (recorded_at - last_recorded_at).total_seconds() < 60:
            return
        last_recorded_candidates[duplicate_key] = recorded_at
    except (TypeError, ValueError):
        pass

    candidate = {
        "timestamp": timestamp,
        "symbol": symbol,
        "entry_price": float(market_price),
        "action": action,
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


def _update_stats(horizon, action, pnl_pct, win):
    action_stats = candidate_stats.setdefault(horizon, {}).setdefault(
        action,
        {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "win_rate": 0.0,
        },
    )

    action_stats["count"] += 1
    if win:
        action_stats["wins"] += 1
    else:
        action_stats["losses"] += 1
    action_stats["total_pnl_pct"] += pnl_pct
    action_stats["avg_pnl_pct"] = action_stats["total_pnl_pct"] / action_stats["count"]
    action_stats["win_rate"] = action_stats["wins"] / action_stats["count"]


def get_market_candidate_stats():
    return deepcopy(candidate_stats)


def get_best_market_candidate_edge(
    min_count=30,
    min_win_rate=0.55,
    min_avg_pnl_pct=0.00015,
    estimated_cost_pct=0.00010,
):
    stats = get_market_candidate_stats()
    best_edge = None

    for horizon, horizon_stats in stats.items():
        for action, action_stats in horizon_stats.items():
            count = action_stats.get("count", 0)
            avg_pnl_pct = action_stats.get("avg_pnl_pct", 0.0)
            win_rate = action_stats.get("win_rate", 0.0)
            net_avg_pnl_pct = avg_pnl_pct - estimated_cost_pct
            if (
                count < min_count
                or win_rate < min_win_rate
                or avg_pnl_pct < min_avg_pnl_pct
                or net_avg_pnl_pct <= 0
            ):
                continue

            edge_score = win_rate * net_avg_pnl_pct
            candidate_edge = {
                "horizon": horizon,
                "action": action,
                "count": count,
                "wins": action_stats.get("wins", 0),
                "losses": action_stats.get("losses", 0),
                "win_rate": win_rate,
                "avg_pnl_pct": avg_pnl_pct,
                "estimated_cost_pct": estimated_cost_pct,
                "net_avg_pnl_pct": net_avg_pnl_pct,
                "edge_score": edge_score,
                "reason": "best reliable positive net edge",
            }

            if best_edge is None or edge_score > best_edge["edge_score"]:
                best_edge = candidate_edge

    if best_edge:
        return best_edge

    return {
        "horizon": None,
        "action": None,
        "count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "avg_pnl_pct": 0.0,
        "estimated_cost_pct": estimated_cost_pct,
        "net_avg_pnl_pct": 0.0,
        "edge_score": 0.0,
        "reason": "no reliable positive net edge",
    }


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
        "decision_action": candidate["decision_action"],
        "decision_confidence": candidate["decision_confidence"],
        "confirmation_count": candidate["confirmation_count"],
        "bullish_count": candidate["bullish_count"],
        "bearish_count": candidate["bearish_count"],
        "bullish_reasons": candidate["bullish_reasons"],
        "bearish_reasons": candidate["bearish_reasons"],
    }
    _update_stats(horizon, action, pnl_pct, event["win"])
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
