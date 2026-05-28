"""下单数量与最小名义价值校验。"""


def normalize_market_buy(exchange, symbol: str, size_usd: float, price: float) -> tuple[float, float]:
    exchange.load_markets()
    market = exchange.market(symbol)
    limits = market.get("limits", {})
    min_cost = limits.get("cost", {}).get("min") or 10.0
    min_amount = limits.get("amount", {}).get("min") or 0.0

    notional = max(float(size_usd), float(min_cost))
    amount = notional / float(price)
    if min_amount:
        amount = max(amount, float(min_amount))

    amount = float(exchange.amount_to_precision(symbol, amount))
    notional = amount * float(price)
    return amount, notional
