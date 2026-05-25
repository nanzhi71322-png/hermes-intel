import os
import time

from loguru import logger


TRADE_COOLDOWN_SECONDS = 10
MOMENTUM_NOISE_THRESHOLD = 0.0003
last_trade_by_symbol = {}
last_price_by_symbol = {}


def _contains_any(text, terms):
    normalized = (text or "").lower()
    return any(term in normalized for term in terms)


def _cooldown_active(symbol):
    if not symbol:
        return False

    last_trade = last_trade_by_symbol.get(symbol)
    if last_trade is None:
        return False

    return time.time() - last_trade < TRADE_COOLDOWN_SECONDS


def mark_trade_opened(symbol):
    if symbol:
        last_trade_by_symbol[symbol] = time.time()


def _price_momentum(symbol, current_price):
    if not symbol or current_price is None:
        return None

    previous_price = last_price_by_symbol.get(symbol)
    last_price_by_symbol[symbol] = current_price

    if previous_price is None:
        return None

    momentum = current_price - previous_price
    direction = "up" if momentum > 0 else "down"
    if not os.getenv("HERMES_BACKTEST"):
        logger.info(f"[momentum] value: {momentum:.2f} direction: {direction}")

    return momentum


def _momentum_allows(action, momentum, current_price):
    if action not in ("long", "short"):
        return True

    if momentum is None or current_price is None:
        return False

    if abs(momentum / current_price) < MOMENTUM_NOISE_THRESHOLD:
        return False

    if action == "long":
        return momentum > 0

    return momentum < 0


def _momentum_is_weak(momentum, current_price):
    if momentum is None or current_price is None:
        return True

    return abs(momentum / current_price) < MOMENTUM_NOISE_THRESHOLD


def _adjust_confidence_for_momentum(confidence, momentum, current_price):
    if _momentum_is_weak(momentum, current_price):
        return max(0, confidence - 10)

    return confidence


def _trade_or_watch(action, confidence, reason, risk, timeframe, momentum, current_price):
    confidence = _adjust_confidence_for_momentum(confidence, momentum, current_price)

    if confidence < 80:
        return {
            "action": "watch",
            "confidence": confidence,
            "reason": "trade confidence below minimum after momentum adjustment",
            "risk": risk,
            "timeframe": timeframe,
        }

    return {
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "risk": risk,
        "timeframe": timeframe,
    }


def generate_decision(signal, alpha, whale, narrative, text, symbol=None, current_price=None):
    alpha_score = alpha.get("alpha_score", 0)
    signal_score = signal.get("score", 0)
    narrative_name = narrative.get("narrative", "unknown")
    whale_detected = whale.get("whale", False)
    momentum = _price_momentum(symbol, current_price)

    if narrative_name == "scam":
        return {
            "action": "watch",
            "confidence": 50,
            "reason": "scam narrative disabled due to poor performance",
            "risk": "low signal quality",
            "timeframe": "short",
        }

    bearish_terms = [
        "liquidation",
        "bearish",
        "sell pressure",
        "outflows",
        "hawkish",
        "risk-off",
        "breakdown",
        "opened short",
    ]
    bullish_terms = [
        "bullish",
        "inflows",
        "approval",
        "approved",
        "breakout",
        "opened long",
        "accumulation",
    ]

    bearish = _contains_any(text, bearish_terms)
    bullish = _contains_any(text, bullish_terms)
    has_trade_catalyst = whale_detected or narrative_name in ("etf", "regulation", "macro", "breaking", "news")
    trade_allowed = (
        alpha_score >= 75
        and signal_score >= 64
        and has_trade_catalyst
    )

    if _cooldown_active(symbol):
        return {
            "action": "watch",
            "confidence": min(70, alpha_score),
            "reason": "symbol cooldown active after recent trade",
            "risk": "overtrading same symbol before signal has time to resolve",
            "timeframe": "short",
        }

    if trade_allowed:
        confidence = _adjust_confidence_for_momentum(
            max(0, min(100, alpha_score)),
            momentum,
            current_price,
        )

        if bullish and bearish and confidence < 80:
            return {
                "action": "watch",
                "confidence": confidence,
                "reason": "mixed bullish and bearish directional signals",
                "risk": "conflicting market signals can reverse quickly",
                "timeframe": "short",
            }

        if bullish and not bearish and confidence >= 70:
            return {
                "action": "long",
                "confidence": confidence,
                "reason": "trade allowed with clean bullish directional signal",
                "risk": "momentum may fade or bullish signal may be crowded",
                "timeframe": "short",
            }

        if bearish and not bullish and confidence >= 70:
            return {
                "action": "short",
                "confidence": confidence,
                "reason": "trade allowed with clean bearish directional signal",
                "risk": "short squeeze or fast reversal against bearish signal",
                "timeframe": "short",
            }

        if confidence >= 80:
            return {
                "action": "long",
                "confidence": confidence,
                "reason": "high confidence signal defaulted to conservative long bias",
                "risk": "unclear direction despite high confidence signal",
                "timeframe": "short",
            }

        return {
            "action": "watch",
            "confidence": confidence,
            "reason": "trade allowed but no clean directional signal above confidence threshold",
            "risk": "unclear direction despite sufficient signal quality",
            "timeframe": "short",
        }

    if (
        trade_allowed
        and whale_detected
        and narrative_name in ("etf", "regulation")
        and alpha_score >= 75
        and _momentum_allows("long", momentum, current_price)
    ):
        return _trade_or_watch(
            "long",
            min(95, alpha_score + 5),
            "whale activity aligns with bullish institutional or regulatory narrative",
            "macro reversal, fake breakout, or headline being misread by the market",
            "short",
            momentum,
            current_price,
        )

    if (
        trade_allowed
        and alpha_score >= 75
        and (bearish or narrative_name == "macro")
        and _momentum_allows("short", momentum, current_price)
    ):
        return _trade_or_watch(
            "short",
            min(92, alpha_score),
            "strong negative or macro-sensitive signal with elevated alpha score",
            "short squeeze, fast policy reversal, or liquidation exhaustion",
            "short",
            momentum,
            current_price,
        )

    if (
        trade_allowed
        and alpha_score >= 75
        and bullish
        and _momentum_allows("long", momentum, current_price)
    ):
        return _trade_or_watch(
            "long",
            min(90, alpha_score),
            "strong bullish market signal with elevated alpha score",
            "fake breakout, delayed confirmation, or crowded positioning",
            "short",
            momentum,
            current_price,
        )

    if 60 <= alpha_score < 75:
        return {
            "action": "watch",
            "confidence": alpha_score,
            "reason": "mixed signal with moderate alpha score",
            "risk": "signal may fade without confirmation from price, volume, or credible follow-through",
            "timeframe": "mid",
        }

    return {
        "action": "ignore",
        "confidence": max(0, min(100, alpha_score)),
        "reason": "low alpha or unclear opportunity",
        "risk": "unclear catalyst and poor signal quality",
        "timeframe": "long",
    }


def _safe_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def adjust_decision_for_market_direction(decision, market_state, price_snapshot):
    adjusted_decision = dict(decision or {})
    market_state = market_state or {}
    price_snapshot = price_snapshot or {}

    original_action = adjusted_decision.get("action")
    final_action = original_action
    market_bias = market_state.get("market_bias")
    score = _safe_number(market_state.get("score"), 0)
    confirmation_count = _safe_number(market_state.get("confirmation_count"), 0)
    current_price = _safe_number(price_snapshot.get("current_price"), None)
    previous_price = _safe_number(price_snapshot.get("previous_price"), None)

    if (
        original_action == "watch"
        and market_bias == "bearish"
        and score >= 85
        and confirmation_count >= 3
        and current_price is not None
        and previous_price is not None
        and current_price < previous_price
    ):
        existing_confidence = _safe_number(adjusted_decision.get("confidence"), 0)
        adjusted_decision["action"] = "short"
        adjusted_decision["confidence"] = min(max(existing_confidence, 80), 95)
        adjusted_decision["reason"] = "strong bearish market_state promotes watch to short"
        final_action = "short"
        return {
            "decision": adjusted_decision,
            "changed": True,
            "original_action": original_action,
            "final_action": final_action,
            "reason": "strong bearish market_state promotes watch to short",
        }

    if original_action == "long" and market_bias == "bearish":
        adjusted_decision["action"] = "watch"
        adjusted_decision["reason"] = "bearish market_state downgrades long to watch"
        final_action = "watch"
        return {
            "decision": adjusted_decision,
            "changed": True,
            "original_action": original_action,
            "final_action": final_action,
            "reason": "bearish market_state downgrades long to watch",
        }

    if original_action == "short" and market_bias != "bearish":
        adjusted_decision["action"] = "watch"
        adjusted_decision["reason"] = "non-bearish market_state downgrades short to watch"
        final_action = "watch"
        return {
            "decision": adjusted_decision,
            "changed": True,
            "original_action": original_action,
            "final_action": final_action,
            "reason": "non-bearish market_state downgrades short to watch",
        }

    return {
        "decision": adjusted_decision,
        "changed": False,
        "original_action": original_action,
        "final_action": final_action,
        "reason": "decision direction unchanged",
    }
