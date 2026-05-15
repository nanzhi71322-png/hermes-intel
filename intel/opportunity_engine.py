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
    strong_momentum = momentum is not None and abs(momentum) > 50
    trade_allowed = (
        (alpha_score >= 60 and signal_score >= 55)
        or (strong_momentum and alpha_score >= 60 and signal_score >= 45)
    )

    if _cooldown_active(symbol):
        return {
            "action": "watch",
            "confidence": min(70, alpha_score),
            "reason": "symbol cooldown active after recent trade",
            "risk": "overtrading same symbol before signal has time to resolve",
            "timeframe": "short",
        }

    if (
        trade_allowed
        and whale_detected
        and narrative_name in ("etf", "regulation")
        and alpha_score >= 75
        and _momentum_allows("long", momentum, current_price)
    ):
        return {
            "action": "long",
            "confidence": min(95, alpha_score + 5),
            "reason": "whale activity aligns with bullish institutional or regulatory narrative",
            "risk": "macro reversal, fake breakout, or headline being misread by the market",
            "timeframe": "short",
        }

    if (
        trade_allowed
        and alpha_score >= 75
        and (bearish or narrative_name == "macro")
        and _momentum_allows("short", momentum, current_price)
    ):
        return {
            "action": "short",
            "confidence": min(92, alpha_score),
            "reason": "strong negative or macro-sensitive signal with elevated alpha score",
            "risk": "short squeeze, fast policy reversal, or liquidation exhaustion",
            "timeframe": "short",
        }

    if (
        trade_allowed
        and alpha_score >= 75
        and bullish
        and _momentum_allows("long", momentum, current_price)
    ):
        return {
            "action": "long",
            "confidence": min(90, alpha_score),
            "reason": "strong bullish market signal with elevated alpha score",
            "risk": "fake breakout, delayed confirmation, or crowded positioning",
            "timeframe": "short",
        }

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
