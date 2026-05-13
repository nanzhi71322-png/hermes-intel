CRITICAL_TRIGGER_TERMS = [
    "confirmed",
    "exploit",
    "halted",
    "frozen",
    "liquidation",
    "approved",
]

CONFIRMED_TERMS = [
    "confirmed",
    "official",
    "verified",
    "announced",
    "reported by",
]

MAJOR_EXPLOIT_TERMS = [
    "major exploit",
    "active exploit",
    "confirmed exploit",
    "confirmed hack",
    "protocol hacked",
    "bridge hacked",
]

EXCHANGE_FREEZE_TERMS = [
    "exchange freeze",
    "withdrawals frozen",
    "withdrawal freeze",
    "withdrawals halted",
    "trading halted",
    "halted withdrawals",
]

REGULATION_PASSED_TERMS = [
    "regulation passed",
    "legislation passed",
    "bill passed",
    "law passed",
    "approved by congress",
    "approved by parliament",
]

LARGE_WHALE_TERMS = [
    ">$100m",
    "> $100m",
    "over $100m",
    "$100m+",
    "$100 million",
    "100 million",
    "nine figures",
]

LIQUIDATION_CASCADE_TERMS = [
    "liquidation cascade",
    "cascade in progress",
    "liquidations accelerating",
    "forced liquidations",
]

HIGH_TERMS = [
    "credible source",
    "clear impact",
    "market impact",
    "actionable",
    "price moved",
    "price movement",
    "flows",
    "inflows",
    "outflows",
    "volume spike",
    "open interest",
    "funding rate",
    "institutional",
    "etf",
    "whale",
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
    "presale",
    "bonus",
    "100x",
    "promo",
    "promotional",
    "airdrop",
]

AGGREGATOR_TERMS = [
    "neome",
    "aggregator",
    "news aggregator",
]

REPEATED_STRUCTURE_TERMS = [
    "same headline",
    "repeated",
    "roundup",
    "summary of posts",
    "multiple posts say",
]


def _contains_any(text, terms):
    return any(term in text for term in terms)


def _has_critical_pattern(text):
    if not _contains_any(text, CRITICAL_TRIGGER_TERMS):
        return False

    confirmed = _contains_any(text, CONFIRMED_TERMS)

    if confirmed and _contains_any(text, MAJOR_EXPLOIT_TERMS):
        return True

    if confirmed and _contains_any(text, EXCHANGE_FREEZE_TERMS):
        return True

    if confirmed and _contains_any(text, REGULATION_PASSED_TERMS):
        return True

    if _contains_any(text, ["whale", "transfer", "movement"]) and _contains_any(text, LARGE_WHALE_TERMS):
        return True

    if _contains_any(text, LIQUIDATION_CASCADE_TERMS):
        return True

    return False


def _downgrade(score, level, reason, text):
    downgrade_reasons = []

    if _contains_any(text, LOW_TERMS):
        downgrade_reasons.append("hype or low-specificity language")

    if _contains_any(text, AGGREGATOR_TERMS):
        downgrade_reasons.append("aggregator source")

    if _contains_any(text, REPEATED_STRUCTURE_TERMS):
        downgrade_reasons.append("repeated or roundup structure")

    if not downgrade_reasons:
        return score, level, reason

    score = min(score, 38 if level == "medium" else 64)

    if score < 40:
        level = "low"
    elif score < 70:
        level = "medium"
    else:
        level = "high"

    reason = f"{reason}; downgraded for {', '.join(downgrade_reasons)}"
    return score, level, reason


def score_signal(text, agent_name=None):
    normalized = (text or "").lower()

    if _has_critical_pattern(normalized):
        return {
            "score": 92,
            "level": "critical",
            "reason": "confirmed major event with explicit critical trigger",
            "should_send": True,
        }

    if _contains_any(normalized, HIGH_TERMS):
        score, level, reason = _downgrade(
            78,
            "high",
            "actionable market information with clear impact",
            normalized,
        )
        return {
            "score": score,
            "level": level,
            "reason": reason,
            "should_send": True,
        }

    if _contains_any(normalized, LOW_TERMS) or len(normalized.strip()) < 240:
        return {
            "score": 28,
            "level": "low",
            "reason": "generic, repeated, or low-specificity content",
            "should_send": True,
        }

    score, level, reason = _downgrade(
        55,
        "medium",
        "useful context but not urgent",
        normalized,
    )

    return {
        "score": score,
        "level": level,
        "reason": reason,
        "should_send": True,
    }
