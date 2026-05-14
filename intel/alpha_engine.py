import re


WHALE_AMOUNT_RE = re.compile(r"\$\s*\d+(?:\.\d+)?\s*(?:m|mn|million|b|bn|billion|\+)", re.IGNORECASE)


def _contains_any(text, terms):
    return any(term in text for term in terms)


def detect_whale_activity(text):
    normalized = (text or "").lower()

    whale_terms = [
        "whale",
        "liquidation",
        "large position",
        "leverage",
        "opened long",
        "opened short",
    ]

    matched_terms = sum(1 for term in whale_terms if term in normalized)
    has_large_amount = bool(WHALE_AMOUNT_RE.search(text or ""))

    if not matched_terms and not has_large_amount:
        return {
            "whale": False,
            "strength": 0,
        }

    strength = 1

    if has_large_amount:
        strength += 1

    if matched_terms >= 2:
        strength += 1

    return {
        "whale": True,
        "strength": min(strength, 3),
    }


def detect_narrative(text):
    normalized = (text or "").lower()

    themes = [
        ("etf", ["etf", "institutional", "blackrock", "fidelity", "spot fund"]),
        ("regulation", ["regulation", "bill", "sec", "legislation", "lawmakers"]),
        ("macro", ["inflation", "fed", "fomc", "rates", "cpi", "macro"]),
        ("meme", ["meme", "hype", "retail", "presale", "100x"]),
        ("scam", ["scam", "rug", "phishing", "wallet drainer", "drainer"]),
    ]

    best_narrative = "unknown"
    best_hits = 0

    for narrative, terms in themes:
        hits = sum(1 for term in terms if term in normalized)
        if hits > best_hits:
            best_narrative = narrative
            best_hits = hits

    if best_hits == 0:
        confidence = 0
    elif best_hits == 1:
        confidence = 0.55
    elif best_hits == 2:
        confidence = 0.75
    else:
        confidence = 0.9

    return {
        "narrative": best_narrative,
        "confidence": confidence,
    }


def compute_alpha(signal, whale, narrative):
    alpha_score = signal.get("score", 0)

    if whale.get("whale"):
        alpha_score += 15

    if narrative.get("narrative") in ("regulation", "etf"):
        alpha_score += 10

    if narrative.get("narrative") == "meme":
        alpha_score -= 10

    alpha_score = max(0, min(100, alpha_score))

    if alpha_score >= 80:
        tag = "alpha"
    elif alpha_score >= 50:
        tag = "neutral"
    else:
        tag = "noise"

    return {
        "alpha_score": alpha_score,
        "tag": tag,
    }
