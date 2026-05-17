def confirm_market_trade(action, current_price, previous_price=None):
    """
    Return dict:
    {
      "confirmed": bool,
      "reason": str,
      "market_score": int
    }
    """
    if action not in ("long", "short"):
        return {
            "confirmed": False,
            "reason": "action is not tradeable",
            "market_score": 0,
        }

    if current_price is None:
        return {
            "confirmed": False,
            "reason": "current price unavailable",
            "market_score": 0,
        }

    if previous_price is None:
        return {
            "confirmed": True,
            "reason": "no previous price available",
            "market_score": 50,
        }

    momentum = (current_price - previous_price) / previous_price

    if abs(momentum) < 0.0002:
        return {
            "confirmed": False,
            "reason": "momentum too weak",
            "market_score": 20,
        }

    if action == "long" and momentum >= 0.0002:
        return {
            "confirmed": True,
            "reason": "market momentum confirms long direction",
            "market_score": 80,
        }

    if action == "short" and momentum <= -0.0002:
        return {
            "confirmed": True,
            "reason": "market momentum confirms short direction",
            "market_score": 80,
        }

    return {
        "confirmed": False,
        "reason": "market momentum does not confirm direction",
        "market_score": 30,
    }
