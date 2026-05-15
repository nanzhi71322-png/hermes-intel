import json
import os

from datetime import datetime

from loguru import logger


DATA_DIR = "data"
PORTFOLIO_FILE = os.path.join(DATA_DIR, "paper_portfolio.json")
STARTING_BALANCE = 100.0
MAX_OPEN_POSITIONS = 3
MIN_UPDATE_AGE_SECONDS = 30
POSITION_TTL_SECONDS = 300

balance = STARTING_BALANCE
positions = []
last_update_price = None
total_trades = 0
win_trades = 0
total_pnl = 0.0


def _valid_price(price):
    if price is None:
        return False

    try:
        price = float(price)
    except (TypeError, ValueError):
        return False

    return 1000 < price <= 300000


def _load_state():
    global balance
    global positions

    if not os.path.exists(PORTFOLIO_FILE):
        return

    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    try:
        loaded_balance = float(state.get("balance", STARTING_BALANCE))
    except (TypeError, ValueError):
        loaded_balance = STARTING_BALANCE

    balance = max(0.0, loaded_balance)
    positions = [
        position for position in state.get("positions", [])
        if position.get("size", 0) >= 0
    ][:MAX_OPEN_POSITIONS]


def _save_state():
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "balance": balance,
            "positions": positions,
        }, f, ensure_ascii=True, indent=2)


def reset_paper_portfolio():
    global balance
    global positions
    global total_trades
    global win_trades
    global total_pnl

    balance = STARTING_BALANCE
    positions = []
    total_trades = 0
    win_trades = 0
    total_pnl = 0.0
    _save_state()

    return {
        "balance": balance,
        "open_positions": len(positions),
    }


def execute_virtual_trade(decision, price, symbol):
    global balance

    _load_state()

    action = decision.get("action")

    if action not in ("long", "short") or not _valid_price(price):
        return None

    if balance <= 0:
        return None

    if len(positions) >= MAX_OPEN_POSITIONS:
        return None

    entry_price = float(price)
    size = min(balance * 0.10, balance)

    if size <= 0:
        return None

    position = {
        "entry_price": entry_price,
        "type": action,
        "size": size,
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
    }

    positions.append(position)
    _save_state()

    return position


def update_positions(current_price, symbol):
    global balance
    global last_update_price
    global total_trades
    global win_trades
    global total_pnl

    _load_state()

    update_key = (symbol, current_price)

    if last_update_price == update_key:
        return {
            "balance": balance,
            "open_positions": len(positions),
        }

    last_update_price = update_key

    if not current_price or current_price < 30000 or current_price > 150000:
        logger.info("invalid price range, skip update")
        return {
            "balance": balance,
            "open_positions": len(positions),
        }

    price = float(current_price)
    open_positions = []

    for position in positions:
        if position.get("symbol") != symbol:
            open_positions.append(position)
            continue

        entry_price = float(position["entry_price"])
        position_size = max(0.0, float(position.get("size", 0)))
        opened_at = datetime.fromisoformat(position["timestamp"])
        age_seconds = (datetime.utcnow() - opened_at).total_seconds()

        if age_seconds <= MIN_UPDATE_AGE_SECONDS:
            open_positions.append(position)
            continue

        if abs(current_price - entry_price) / entry_price > 0.6:
            logger.info("abnormal price deviation >60%, skip pnl update")
            open_positions.append(position)
            continue

        if position_size <= 0 or entry_price <= 0:
            continue

        if position["type"] == "short":
            pnl_pct = (entry_price - price) / entry_price
        else:
            pnl_pct = (price - entry_price) / entry_price

        if abs(pnl_pct) > 0.20:
            logger.info("invalid pnl jump, skip update")
            open_positions.append(position)
            continue

        if pnl_pct >= 0.01 or pnl_pct <= -0.01 or age_seconds > POSITION_TTL_SECONDS:
            pnl = position_size * pnl_pct
            balance = max(0.0, balance + pnl)
            total_trades += 1
            total_pnl += pnl
            if pnl > 0:
                win_trades += 1
            win_rate = (win_trades / total_trades) * 100 if total_trades else 0
            logger.info(f"[trade closed] pnl: {pnl:.2f} balance: {balance:.2f}")
            logger.info(
                f"[stats] trades: {total_trades} "
                f"win_rate: {win_rate:.2f} "
                f"total_pnl: {total_pnl:.2f} "
                f"balance: {balance:.2f}"
            )
        else:
            open_positions.append(position)

    positions[:] = open_positions[:MAX_OPEN_POSITIONS]
    _save_state()

    logger.info(f"[portfolio] balance: {balance:.2f} | open_positions: {len(positions)}")

    return {
        "balance": balance,
        "open_positions": len(positions),
    }


_load_state()
