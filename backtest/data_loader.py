"""历史 K 线数据采集与本地缓存。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ccxt
import pandas as pd
from loguru import logger


DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "backtest"


def _cache_path(symbol: str, timeframe: str) -> Path:
    """生成缓存文件路径。"""
    safe_symbol = symbol.replace("/", "-")
    return DATA_ROOT / f"{safe_symbol}_{timeframe}.csv"


def fetch_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    limit: int = 1000,
    exchange_id: str = "binance",
    since_ms: Optional[int] = None,
) -> pd.DataFrame:
    """从交易所拉取 OHLCV 并返回标准 DataFrame。"""
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    all_rows: list[list] = []
    cursor = since_ms

    while len(all_rows) < limit:
        batch_limit = min(1000, limit - len(all_rows))
        rows = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=batch_limit)
        if not rows:
            break
        all_rows.extend(rows)
        cursor = rows[-1][0] + 1
        if len(rows) < batch_limit:
            break

    if not all_rows:
        raise ValueError(f"未获取到 {symbol} {timeframe} 数据")

    df = pd.DataFrame(
        all_rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return df.reset_index(drop=True)


def load_or_fetch(
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    limit: int = 5000,
    exchange_id: str = "binance",
    refresh: bool = False,
) -> pd.DataFrame:
    """优先读本地缓存，缺失或 refresh 时重新下载。"""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(symbol, timeframe)

    if cache_file.exists() and not refresh:
        logger.info(f"从缓存加载: {cache_file}")
        df = pd.read_csv(cache_file, parse_dates=["datetime"])
        if len(df) >= limit:
            return df.tail(limit).reset_index(drop=True)

    logger.info(f"下载 {symbol} {timeframe} limit={limit}")
    since_days = max(7, limit // 1440 + 2)
    since_ms = int(
        datetime.now(timezone.utc).timestamp() * 1000 - since_days * 86400 * 1000
    )
    df = fetch_ohlcv(symbol, timeframe, limit=limit, exchange_id=exchange_id, since_ms=since_ms)
    df.to_csv(cache_file, index=False)
    logger.info(f"已缓存 {len(df)} 条到 {cache_file}")
    return df
