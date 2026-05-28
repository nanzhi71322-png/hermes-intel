"""Agent/keyword 名称到 CCXT 交易对映射。"""

AGENT_TO_CCXT = {
    "btc": "BTC/USDT",
    "bitcoin": "BTC/USDT",
    "breaking": "BTC/USDT",
    "scam": "BTC/USDT",
    "eth": "ETH/USDT",
    "ethereum": "ETH/USDT",
    "sol": "SOL/USDT",
    "solana": "SOL/USDT",
}

UNDERLYING_TO_CCXT = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
}


def resolve_ccxt_symbol(source_key: str, default: str = "BTC/USDT") -> str:
    if not source_key:
        return default

    normalized = str(source_key).strip().lower()
    if normalized in AGENT_TO_CCXT:
        return AGENT_TO_CCXT[normalized]

    upper = str(source_key).strip().upper()
    if upper in UNDERLYING_TO_CCXT:
        return UNDERLYING_TO_CCXT[upper]

    if "/" in str(source_key):
        return str(source_key)

    if upper.endswith("USDT") and len(upper) > 4:
        base = upper[:-4]
        return f"{base}/USDT"

    return default


def resolve_underlying_asset(source_key: str, default: str = "BTCUSDT") -> str:
    ccxt_symbol = resolve_ccxt_symbol(source_key, default.replace("USDT", "/USDT"))
    return ccxt_symbol.replace("/", "")
