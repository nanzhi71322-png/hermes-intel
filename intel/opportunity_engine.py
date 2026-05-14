def _contains_any(text, terms):
    normalized = (text or "").lower()
    return any(term in normalized for term in terms)


def generate_decision(signal, alpha, whale, narrative, text):
    alpha_score = alpha.get("alpha_score", 0)
    narrative_name = narrative.get("narrative", "unknown")
    whale_detected = whale.get("whale", False)

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

    if whale_detected and narrative_name in ("etf", "regulation") and alpha_score >= 75:
        return {
            "action": "long",
            "confidence": min(95, alpha_score + 5),
            "reason": "whale activity aligns with bullish institutional or regulatory narrative",
            "risk": "macro reversal, fake breakout, or headline being misread by the market",
            "timeframe": "short",
        }

    if alpha_score >= 75 and (bearish or narrative_name == "macro"):
        return {
            "action": "short",
            "confidence": min(92, alpha_score),
            "reason": "strong negative or macro-sensitive signal with elevated alpha score",
            "risk": "short squeeze, fast policy reversal, or liquidation exhaustion",
            "timeframe": "short",
        }

    if alpha_score >= 75 and bullish:
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
