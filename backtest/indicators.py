"""技术指标计算 — 复刻 intel/market_state.py 的 K 线逻辑。"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def bollinger_position(closes: list[float]) -> str:
    """计算价格在布林带中的位置。"""
    if len(closes) < 20:
        return "unknown"

    latest = closes[-1]
    middle = sum(closes) / len(closes)
    variance = sum((c - middle) ** 2 for c in closes) / len(closes)
    std = math.sqrt(variance)
    upper = middle + 2 * std
    lower = middle - 2 * std

    if latest > upper:
        return "outside_upper"
    if latest > middle:
        return "upper"
    if latest < lower:
        return "outside_lower"
    if latest < middle:
        return "lower"
    return "middle"


def breakout_signal(highs: list[float], lows: list[float], latest_close: float) -> str:
    """检测是否突破近期高低点。"""
    if len(highs) < 20 or len(lows) < 20:
        return "unknown"
    if latest_close > max(highs):
        return "up"
    if latest_close < min(lows):
        return "down"
    return "none"


def volume_ratio(volumes: list[float]) -> Optional[float]:
    """最新成交量 / 过去20根均量。"""
    if len(volumes) < 21:
        return None
    latest = volumes[-1]
    avg = sum(volumes[-21:-1]) / 20
    if avg <= 0:
        return None
    return latest / avg


def compute_market_state_row(window: pd.DataFrame) -> dict:
    """对滑动窗口计算 market_state 结构（不含 orderbook）。"""
    closes = window["close"].astype(float).tolist()
    highs = window["high"].astype(float).tolist()
    lows = window["low"].astype(float).tolist()
    volumes = window["volume"].astype(float).tolist()

    bb_pos = bollinger_position(closes[-20:])
    brk = breakout_signal(highs[-21:-1], lows[-21:-1], closes[-1])
    vol_ratio = volume_ratio(volumes)

    bullish: list[str] = []
    bearish: list[str] = []

    if vol_ratio is not None and vol_ratio >= 1.5:
        bullish.append("volume_expansion")
        bearish.append("volume_expansion")
    if brk == "up":
        bullish.append("breakout_up")
    if bb_pos in ("upper", "outside_upper"):
        bullish.append("upper_band_position")
    if brk == "down":
        bearish.append("breakout_down")
    if bb_pos in ("lower", "outside_lower"):
        bearish.append("lower_band_position")

    bull_count = len(bullish)
    bear_count = len(bearish)

    if bull_count >= 2:
        bias, confirm = "bullish", bull_count
    elif bear_count >= 2:
        bias, confirm = "bearish", bear_count
    else:
        bias, confirm = "neutral", 0

    if bias in ("bullish", "bearish") and confirm >= 3:
        score = 85
    elif bias in ("bullish", "bearish") and confirm == 2:
        score = 70
    elif bb_pos != "unknown" and brk != "unknown":
        score = 50
    else:
        bias, score = "unknown", 20

    return {
        "market_bias": bias,
        "score": score,
        "confirmation_count": confirm,
        "bb_position": bb_pos,
        "breakout": brk,
        "volume_ratio_1m": vol_ratio,
        "bullish_count": bull_count,
        "bearish_count": bear_count,
        "price": closes[-1],
    }


def enrich_dataframe(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """为每根 K 线附加 market_state 字段。"""
    records: list[dict] = []
    for i in range(len(df)):
        if i < lookback:
            records.append({"market_bias": "unknown", "score": 20, "confirmation_count": 0})
            continue
        state = compute_market_state_row(df.iloc[i - lookback + 1 : i + 1])
        records.append(state)
    enriched = pd.concat([df.reset_index(drop=True), pd.DataFrame(records)], axis=1)
    return enriched
