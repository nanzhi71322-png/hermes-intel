import math

import requests


BINANCE_BASE_URL = "https://api.binance.com"
REQUEST_TIMEOUT = 5


def _unknown_state(symbol, reason):
    return {
        "symbol": symbol,
        "price": None,
        "volume_1m": None,
        "volume_5m": None,
        "volume_ratio_1m": None,
        "orderbook_imbalance": None,
        "bid_depth": None,
        "ask_depth": None,
        "bb_position": "unknown",
        "breakout": "unknown",
        "market_bias": "unknown",
        "score": 20,
        "reason": reason,
        "bullish_count": 0,
        "bearish_count": 0,
        "confirmation_count": 0,
        "bullish_reasons": [],
        "bearish_reasons": [],
    }


def _get_json(path, params):
    response = requests.get(
        f"{BINANCE_BASE_URL}{path}",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _volume_ratio_1m(klines):
    if len(klines) < 21:
        return None

    latest_volume = _float(klines[-1][5])
    previous_volumes = [_float(kline[5]) for kline in klines[-21:-1]]
    previous_volumes = [volume for volume in previous_volumes if volume is not None]

    if latest_volume is None or not previous_volumes:
        return None

    average_volume = sum(previous_volumes) / len(previous_volumes)
    if average_volume <= 0:
        return None

    return latest_volume / average_volume


def _bollinger_position(klines):
    if len(klines) < 20:
        return "unknown"

    closes = [_float(kline[4]) for kline in klines[-20:]]
    if any(close is None for close in closes):
        return "unknown"

    latest_close = closes[-1]
    middle = sum(closes) / len(closes)
    variance = sum((close - middle) ** 2 for close in closes) / len(closes)
    std = math.sqrt(variance)
    upper = middle + 2 * std
    lower = middle - 2 * std

    if latest_close > upper:
        return "outside_upper"
    if latest_close > middle:
        return "upper"
    if latest_close < lower:
        return "outside_lower"
    if latest_close < middle:
        return "lower"

    return "middle"


def _breakout(klines):
    if len(klines) < 21:
        return "unknown"

    latest_close = _float(klines[-1][4])
    previous_highs = [_float(kline[2]) for kline in klines[-21:-1]]
    previous_lows = [_float(kline[3]) for kline in klines[-21:-1]]

    if (
        latest_close is None
        or any(high is None for high in previous_highs)
        or any(low is None for low in previous_lows)
    ):
        return "unknown"

    if latest_close > max(previous_highs):
        return "up"
    if latest_close < min(previous_lows):
        return "down"

    return "none"


def _depth_value(levels):
    total = 0.0
    for price, quantity in levels:
        price_value = _float(price)
        quantity_value = _float(quantity)
        if price_value is None or quantity_value is None:
            continue
        total += price_value * quantity_value
    return total


def get_btc_market_state(symbol="BTCUSDT"):
    try:
        ticker = _get_json("/api/v3/ticker/price", {"symbol": symbol})
        klines_1m = _get_json(
            "/api/v3/klines",
            {"symbol": symbol, "interval": "1m", "limit": 60},
        )
        klines_5m = _get_json(
            "/api/v3/klines",
            {"symbol": symbol, "interval": "5m", "limit": 60},
        )
        depth = _get_json("/api/v3/depth", {"symbol": symbol, "limit": 50})
    except requests.RequestException as exc:
        return _unknown_state(symbol, f"api error: {exc}")
    except Exception as exc:
        return _unknown_state(symbol, f"market state error: {exc}")

    try:
        price = _float(ticker.get("price"))
        volume_1m = _float(klines_1m[-1][5]) if klines_1m else None
        volume_5m = _float(klines_5m[-1][5]) if klines_5m else None
        volume_ratio_1m = _volume_ratio_1m(klines_1m)
        bid_depth = _depth_value(depth.get("bids", []))
        ask_depth = _depth_value(depth.get("asks", []))

        orderbook_imbalance = None
        depth_total = bid_depth + ask_depth
        if depth_total > 0:
            orderbook_imbalance = (bid_depth - ask_depth) / depth_total

        bb_position = _bollinger_position(klines_1m)
        breakout = _breakout(klines_1m)

        bullish_reasons = []
        bearish_reasons = []

        if orderbook_imbalance is not None and orderbook_imbalance > 0.08:
            bullish_reasons.append("orderbook_bid_pressure")
        if volume_ratio_1m is not None and volume_ratio_1m >= 1.5:
            bullish_reasons.append("volume_expansion")
            bearish_reasons.append("volume_expansion")
        if breakout == "up":
            bullish_reasons.append("breakout_up")
        if bb_position in ("upper", "outside_upper"):
            bullish_reasons.append("upper_band_position")

        if orderbook_imbalance is not None and orderbook_imbalance < -0.08:
            bearish_reasons.append("orderbook_ask_pressure")
        if breakout == "down":
            bearish_reasons.append("breakout_down")
        if bb_position in ("lower", "outside_lower"):
            bearish_reasons.append("lower_band_position")

        bullish_count = len(bullish_reasons)
        bearish_count = len(bearish_reasons)

        if bullish_count >= 2:
            market_bias = "bullish"
            confirmation_count = bullish_count
        elif bearish_count >= 2:
            market_bias = "bearish"
            confirmation_count = bearish_count
        else:
            market_bias = "neutral"
            confirmation_count = 0

        if market_bias in ("bullish", "bearish") and confirmation_count >= 3:
            score = 85
        elif market_bias in ("bullish", "bearish") and confirmation_count == 2:
            score = 70
        elif all(
            value is not None
            for value in (
                price,
                volume_1m,
                volume_5m,
                volume_ratio_1m,
                orderbook_imbalance,
                bid_depth,
                ask_depth,
            )
        ) and bb_position != "unknown" and breakout != "unknown":
            score = 50
        else:
            market_bias = "unknown"
            score = 20

        if market_bias == "bullish":
            active_reasons = bullish_reasons
        elif market_bias == "bearish":
            active_reasons = bearish_reasons
        else:
            active_reasons = bullish_reasons + bearish_reasons

        reason = (
            f"{market_bias} bullish_count={bullish_count} "
            f"bearish_count={bearish_count} reasons={','.join(active_reasons)}"
        )

        return {
            "symbol": symbol,
            "price": price,
            "volume_1m": volume_1m,
            "volume_5m": volume_5m,
            "volume_ratio_1m": volume_ratio_1m,
            "orderbook_imbalance": orderbook_imbalance,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "bb_position": bb_position,
            "breakout": breakout,
            "market_bias": market_bias,
            "score": score,
            "reason": reason,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "confirmation_count": confirmation_count,
            "bullish_reasons": bullish_reasons,
            "bearish_reasons": bearish_reasons,
        }
    except Exception as exc:
        return _unknown_state(symbol, f"calculation error: {exc}")


def build_market_candidate(market_state):
    market_bias = market_state.get("market_bias")
    score = market_state.get("score", 0)
    confirmation_count = market_state.get("confirmation_count", 0)

    if market_bias == "bullish" and score >= 85 and confirmation_count >= 3:
        return {
            "action": "long",
            "confidence": 80,
            "reason": "strong bullish market structure candidate",
        }

    if market_bias == "bearish" and score >= 85 and confirmation_count >= 3:
        return {
            "action": "short",
            "confidence": 80,
            "reason": "strong bearish market structure candidate",
        }

    if market_bias == "bullish" and score >= 70 and confirmation_count >= 2:
        return {
            "action": "watch",
            "confidence": 65,
            "reason": "bullish setup but not strong enough for autonomous candidate",
        }

    if market_bias == "bearish" and score >= 70 and confirmation_count >= 2:
        return {
            "action": "watch",
            "confidence": 65,
            "reason": "bearish setup but not strong enough for autonomous candidate",
        }

    return {
        "action": "watch",
        "confidence": 50,
        "reason": "market structure has no autonomous candidate",
    }


def confirm_market_state_for_execution(action, market_state):
    market_state = market_state or {}
    market_bias = market_state.get("market_bias", "unknown")
    score = market_state.get("score", 0) or 0
    confirmation_count = market_state.get("confirmation_count", 0) or 0

    if action == "long":
        if market_bias == "neutral":
            reason = "market_state neutral blocks execution"
        elif market_bias != "bullish":
            reason = "market_state direction mismatch"
        elif score < 70:
            reason = "market_state score too weak"
        elif confirmation_count < 2:
            reason = "market_state confirmation_count too weak"
        else:
            return {
                "confirmed": True,
                "score": int(score),
                "reason": "market_state confirms long",
            }
    elif action == "short":
        if market_bias == "neutral":
            reason = "market_state neutral blocks execution"
        elif market_bias != "bearish":
            reason = "market_state direction mismatch"
        elif score < 70:
            reason = "market_state score too weak"
        elif confirmation_count < 2:
            reason = "market_state confirmation_count too weak"
        else:
            return {
                "confirmed": True,
                "score": int(score),
                "reason": "market_state confirms short",
            }
    else:
        reason = "market_state action is not tradeable"

    return {
        "confirmed": False,
        "score": int(score),
        "reason": reason,
    }


def confirm_long_quality_for_execution(action, market_state):
    market_state = market_state or {}

    score = market_state.get("score", 0) or 0
    confirmation_count = market_state.get("confirmation_count", 0) or 0
    breakout = market_state.get("breakout")
    bb_position = market_state.get("bb_position") or market_state.get("bb")
    market_bias = market_state.get("market_bias")

    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    try:
        confirmation_count = int(confirmation_count)
    except (TypeError, ValueError):
        confirmation_count = 0

    if action != "long":
        return {
            "confirmed": True,
            "score": score,
            "reason": "non-long action bypasses long quality filter",
        }

    if market_bias != "bullish":
        return {
            "confirmed": False,
            "score": score,
            "reason": "long quality blocks non-bullish market_state",
        }

    if score < 85 and confirmation_count < 3 and breakout != "up":
        return {
            "confirmed": False,
            "score": score,
            "reason": "long quality too weak without breakout",
        }

    if breakout == "up":
        reason = "long quality confirms breakout up"
    elif confirmation_count >= 3:
        reason = "long quality confirms high confirmation count"
    else:
        reason = "long quality confirms strong bullish structure"

    return {
        "confirmed": True,
        "score": score,
        "reason": reason,
    }
