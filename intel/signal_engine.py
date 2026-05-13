CRITICAL_TERMS = [
    "active hack",
    "exploit",
    "wallet drainer",
    "drainer",
    "exchange freeze",
    "withdrawals frozen",
    "withdrawal freeze",
    "etf approval",
    "legislation passed",
    "law passed",
    "whale movement",
    "liquidation cascade",
    "over $100m",
    "$100m",
    "100 million",
]

HIGH_TERMS = [
    "confirmed",
    "official",
    "credible source",
    "breaking",
    "market impact",
    "actionable",
    "major announcement",
    "institutional",
    "etf",
    "whale",
    "hack",
    "exploit",
    "liquidation",
]

LOW_TERMS = [
    "rumor",
    "influencer",
    "hype",
    "clickbait",
    "generic",
    "vague",
    "sentiment",
    "repeated headline",
    "no clear catalyst",
]


def _contains_any(text, terms):
    return any(term in text for term in terms)


def score_signal(text, agent_name=None):
    normalized = (text or "").lower()

    if _contains_any(normalized, CRITICAL_TERMS):
        return {
            "score": 92,
            "level": "critical",
            "reason": "major breaking event or large financial/policy impact detected",
            "should_send": True,
        }

    if _contains_any(normalized, HIGH_TERMS):
        return {
            "score": 78,
            "level": "high",
            "reason": "actionable market-related information detected",
            "should_send": True,
        }

    if _contains_any(normalized, LOW_TERMS) or len(normalized.strip()) < 240:
        return {
            "score": 28,
            "level": "low",
            "reason": "generic, repeated, or low-specificity content",
            "should_send": True,
        }

    return {
        "score": 55,
        "level": "medium",
        "reason": "useful context but not urgent",
        "should_send": True,
    }
