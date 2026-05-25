"""市场状态识别 — 牛市 / 震荡 / 熊市。"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Regime = Literal["bull", "bear", "sideways", "unknown"]

# 5m 周期默认：288 bar ≈ 1 天，576 bar ≈ 2 天
DEFAULT_LOOKBACK = 288
BULL_RETURN = 0.012
BEAR_RETURN = -0.012


def detect_regime(closes: list[float], lookback: int = DEFAULT_LOOKBACK) -> Regime:
    """根据趋势斜率 + 均线排列判断市场状态。"""
    if len(closes) < max(lookback, 60) + 1:
        return "unknown"

    window = closes[-lookback:]
    start, end = window[0], window[-1]
    if start <= 0:
        return "unknown"

    ret = (end - start) / start
    sma20 = sum(closes[-20:]) / 20
    sma60 = sum(closes[-60:]) / 60

    if ret >= BULL_RETURN and end >= sma20 >= sma60:
        return "bull"
    if ret <= BEAR_RETURN and end <= sma20 <= sma60:
        return "bear"
    return "sideways"


def enrich_regime(df: pd.DataFrame, lookback: int = DEFAULT_LOOKBACK) -> pd.DataFrame:
    """为每根 K 线附加 market_regime 字段。"""
    closes = df["close"].astype(float).tolist()
    regimes: list[str] = []
    for i in range(len(closes)):
        if i < lookback:
            regimes.append("unknown")
        else:
            regimes.append(detect_regime(closes[: i + 1], lookback))
    out = df.copy().reset_index(drop=True)
    out["market_regime"] = regimes
    return out


def regime_bar_counts(df: pd.DataFrame) -> dict[str, int]:
    """统计各状态 K 线数量。"""
    if "market_regime" not in df.columns:
        df = enrich_regime(df)
    counts = df["market_regime"].value_counts().to_dict()
    return {str(k): int(v) for k, v in counts.items()}
