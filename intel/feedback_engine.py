import json
import os
import re
from datetime import datetime

from loguru import logger

from config.settings import BOT_HOME


FEEDBACK_FILE = os.path.join(BOT_HOME, "decision_feedback.jsonl")
PRICE_PATTERNS = [
    re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?", re.IGNORECASE),
    re.compile(r"\b(\d+(?:\.\d+)?)\s*k\b", re.IGNORECASE),
    re.compile(r"\b(\d{5,6}(?:\.\d+)?)\b"),
]
BTC_CONTEXT_TERMS = [
    "btc",
    "bitcoin",
]
IGNORE_PRICE_TERMS = [
    "target",
    "prediction",
    "forecast",
    "could",
    "might",
    "will",
    "expect",
    "scenario",
]


def extract_price_from_text(text):
    raw = text or ""
    normalized = raw.lower()
    candidates = []

    if not any(term in normalized for term in BTC_CONTEXT_TERMS):
        return None

    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(raw):
            start, end = match.span()
            window_start = max(0, start - 50)
            window_end = min(len(raw), end + 50)
            window = normalized[window_start:window_end]

            btc_positions = []
            for term in BTC_CONTEXT_TERMS:
                term_index = window.find(term)
                while term_index != -1:
                    btc_positions.append(window_start + term_index)
                    term_index = window.find(term, term_index + len(term))

            if not btc_positions:
                continue

            if any(term in window for term in IGNORE_PRICE_TERMS):
                continue

            value = match.group(1).replace(",", "")

            try:
                price = float(value)
            except ValueError:
                continue

            has_k_suffix = bool(match.group(2)) if len(match.groups()) > 1 else "k" in match.group(0).lower()
            if has_k_suffix:
                price *= 1000

            if 30000 <= price <= 150000:
                distance = min(abs(start - btc_position) for btc_position in btc_positions)
                if distance < 50:
                    candidates.append((distance, price))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _decision_age_seconds(decision) -> float:
    """决策距今秒数，用于延迟评估避免同价误判。"""
    ts = decision.get("timestamp")
    if not ts:
        return 9999.0
    try:
        opened = datetime.fromisoformat(str(ts).replace("Z", ""))
        return (datetime.utcnow() - opened).total_seconds()
    except (TypeError, ValueError):
        return 9999.0


def record_decision(timestamp, decision, price_at_decision, symbol):
    record = {
        "timestamp": timestamp,
        "symbol": symbol,
        "action": decision.get("action"),
        "confidence": decision.get("confidence"),
        "price": price_at_decision,
        "narrative": decision.get("narrative", "unknown"),
        "timeframe": decision.get("timeframe"),
    }

    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")

    return record


def _load_decisions():
    if not os.path.exists(FEEDBACK_FILE):
        return []

    decisions = []

    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                decisions.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return decisions


def _write_decisions(decisions):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        for decision in decisions:
            f.write(json.dumps(decision, ensure_ascii=True) + "\n")


def evaluate_outcome(decision, current_price):
    entry_price = decision.get("price")
    action = decision.get("action")

    if entry_price is None or current_price is None:
        return {
            "result": "neutral",
            "pnl_estimate": "0.00%",
            "correct": False,
        }

    try:
        entry_price = float(entry_price)
        current_price = float(current_price)
    except (TypeError, ValueError):
        return {
            "result": "neutral",
            "pnl_estimate": "0.00%",
            "correct": False,
        }

    if entry_price == 0:
        pnl = 0
    elif action == "short":
        pnl = ((entry_price - current_price) / entry_price) * 100
    else:
        pnl = ((current_price - entry_price) / entry_price) * 100

    if action == "long":
        correct = current_price > entry_price
    elif action == "short":
        correct = current_price < entry_price
    else:
        correct = False

    if abs(pnl) < 0.1:
        result = "neutral"
    elif correct:
        result = "win"
    else:
        result = "loss"

    return {
        "result": result,
        "pnl_estimate": f"{pnl:.2f}%",
        "correct": correct,
    }


def evaluate_decisions(current_price=None):
    from intel.market_price import get_btc_price

    if current_price is None:
        current_price = get_btc_price()

    decisions = _load_decisions()
    evaluations = []
    changed = False

    for decision in decisions:
        if decision.get("result"):
            continue

        if decision.get("price") is None:
            continue

        if _decision_age_seconds(decision) < 60:
            continue

        if current_price is None:
            continue

        outcome = evaluate_outcome(decision, current_price)

        decision.update({
            "current_price": current_price,
            "result": outcome["result"],
            "pnl_estimate": outcome["pnl_estimate"],
            "correct": outcome["correct"],
        })

        evaluations.append({
            "result": outcome["result"],
            "correct": outcome["correct"],
        })
        changed = True

    if changed:
        _write_decisions(decisions)
        stats = compute_statistics()
        if stats["total_trades"] and stats["total_trades"] % 10 == 0:
            logger.info(
                "performance summary: "
                f"total={stats['total_trades']} "
                f"long_win_rate={stats['long_win_rate']}% "
                f"short_win_rate={stats['short_win_rate']}% "
                f"best_narrative={stats['best_narrative']} "
                f"worst_narrative={stats['worst_narrative']}"
            )

    return evaluations


def _win_rate(records):
    if not records:
        return 0

    wins = sum(1 for record in records if record.get("correct") is True)
    return round((wins / len(records)) * 100, 2)


def compute_statistics():
    decisions = _load_decisions()
    evaluated = [decision for decision in decisions if decision.get("result")]

    long_records = [decision for decision in evaluated if decision.get("action") == "long"]
    short_records = [decision for decision in evaluated if decision.get("action") == "short"]

    narrative_scores = {}

    for decision in evaluated:
        narrative = decision.get("narrative") or "unknown"
        if narrative not in narrative_scores:
            narrative_scores[narrative] = {
                "total": 0,
                "wins": 0,
            }

        narrative_scores[narrative]["total"] += 1
        if decision.get("correct") is True:
            narrative_scores[narrative]["wins"] += 1

    best_narrative = "unknown"
    worst_narrative = "unknown"

    if narrative_scores:
        ranked = sorted(
            narrative_scores.items(),
            key=lambda item: item[1]["wins"] / item[1]["total"],
        )
        worst_narrative = ranked[0][0]
        best_narrative = ranked[-1][0]

    return {
        "long_win_rate": _win_rate(long_records),
        "short_win_rate": _win_rate(short_records),
        "total_trades": len(evaluated),
        "best_narrative": best_narrative,
        "worst_narrative": worst_narrative,
    }
