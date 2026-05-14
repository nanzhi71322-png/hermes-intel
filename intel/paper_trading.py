from datetime import datetime

from loguru import logger


balance = 100.0
positions = []


def execute_virtual_trade(decision, price):
    global balance

    action = decision.get("action")

    if action not in ("long", "short") or price is None:
        return None

    try:
        entry_price = float(price)
    except (TypeError, ValueError):
        return None

    if entry_price <= 0:
        return None

    size = balance * 0.10

    position = {
        "entry_price": entry_price,
        "type": action,
        "size": size,
        "timestamp": datetime.utcnow().isoformat(),
    }

    positions.append(position)
    return position


def update_positions(current_price):
    global balance

    if current_price is None:
        logger.info(f"[portfolio] balance: {balance:.2f} | open_positions: {len(positions)}")
        return {
            "balance": balance,
            "open_positions": len(positions),
        }

    try:
        price = float(current_price)
    except (TypeError, ValueError):
        logger.info(f"[portfolio] balance: {balance:.2f} | open_positions: {len(positions)}")
        return {
            "balance": balance,
            "open_positions": len(positions),
        }

    open_positions = []

    for position in positions:
        entry_price = position["entry_price"]

        if position["type"] == "short":
            pnl_pct = ((entry_price - price) / entry_price) * 100
        else:
            pnl_pct = ((price - entry_price) / entry_price) * 100

        if pnl_pct > 3 or pnl_pct < -2:
            balance += position["size"] * (pnl_pct / 100)
        else:
            open_positions.append(position)

    positions[:] = open_positions

    logger.info(f"[portfolio] balance: {balance:.2f} | open_positions: {len(positions)}")

    return {
        "balance": balance,
        "open_positions": len(positions),
    }
