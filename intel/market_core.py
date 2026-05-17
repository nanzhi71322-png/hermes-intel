def confirm_market_core(action, price_snapshot):
    if action not in ("long", "short"):
        return {"confirmed": False, "score": 0, "reason": "invalid action"}

    current_price = price_snapshot.get("current_price")
    previous_price = price_snapshot.get("previous_price")

    if current_price is None:
        return {"confirmed": False, "score": 0, "reason": "no price"}

    if previous_price is None:
        return {"confirmed": True, "score": 50, "reason": "no previous price"}

    momentum = (current_price - previous_price) / previous_price

    score = 0

    if action == "long" and momentum > 0:
        score += 30
    elif action == "short" and momentum < 0:
        score += 30

    if abs(momentum) < 0.001:
        return {"confirmed": False, "score": 20, "reason": "momentum too weak"}

    if score >= 30:
        return {"confirmed": True, "score": score, "reason": "basic momentum confirm"}

    return {"confirmed": False, "score": score, "reason": "no confirmation"}
