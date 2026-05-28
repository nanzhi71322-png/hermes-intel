"""Live 持仓与订单持久化。"""
import json
import os
from datetime import datetime

from config.settings import BOT_HOME

DATA_DIR = os.path.join(BOT_HOME, "data")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "live_portfolio.json")
ORDERS_FILE = os.path.join(DATA_DIR, "live_orders.jsonl")
CLOSED_FILE = os.path.join(DATA_DIR, "live_closed.jsonl")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def load_all_positions() -> list[dict]:
    _ensure_data_dir()
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return payload.get("positions", [])


def load_positions() -> list[dict]:
    return [p for p in load_all_positions() if p.get("status", "open") == "open"]


def save_positions(positions: list[dict]) -> None:
    _ensure_data_dir()
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as handle:
        json.dump({"positions": positions}, handle, ensure_ascii=True, indent=2)


def append_position(position: dict) -> None:
    positions = load_all_positions()
    positions.append(position)
    save_positions(positions)


def update_position(position: dict) -> None:
    positions = load_all_positions()
    for idx, existing in enumerate(positions):
        if existing.get("order_id") == position.get("order_id") and existing.get("timestamp") == position.get("timestamp"):
            positions[idx] = position
            save_positions(positions)
            return
    positions.append(position)
    save_positions(positions)


def append_order_record(record: dict) -> None:
    _ensure_data_dir()
    record = dict(record)
    record.setdefault("timestamp", datetime.utcnow().isoformat())
    with open(ORDERS_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def append_closed_record(record: dict) -> None:
    _ensure_data_dir()
    record = dict(record)
    record.setdefault("closed_at", datetime.utcnow().isoformat())
    with open(CLOSED_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def recent_orders(limit: int = 5) -> list[dict]:
    return _read_jsonl_tail(ORDERS_FILE, limit)


def recent_closed(limit: int = 20) -> list[dict]:
    return _read_jsonl_tail(CLOSED_FILE, limit)


def _read_jsonl_tail(path: str, limit: int) -> list[dict]:
    if not os.path.exists(path):
        return []
    lines: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                lines.append(line)
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def closed_stats(limit: int = 100) -> dict:
    records = recent_closed(limit)
    if not records:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0}

    wins = sum(1 for r in records if float(r.get("pnl", 0)) > 0)
    total_pnl = sum(float(r.get("pnl", 0)) for r in records)
    count = len(records)
    return {
        "count": count,
        "wins": wins,
        "losses": count - wins,
        "win_rate": wins / count if count else 0.0,
        "total_pnl": total_pnl,
    }
