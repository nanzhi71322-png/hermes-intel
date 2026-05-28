"""CCXT 行情服务；失败时回退到 intel/market_state。"""

from loguru import logger

from config.trading import DEFAULT_SYMBOL
from intel.market_state import get_btc_market_state


class MarketDataService:
    def __init__(self, connector=None):
        self.connector = connector

    def get_market_state(self, symbol: str = "BTCUSDT") -> dict:
        if self.connector is None:
            return get_btc_market_state(symbol)

        ccxt_symbol = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        try:
            ticker = self.connector.fetch_ticker(ccxt_symbol)
            price = ticker.get("last")
            state = get_btc_market_state(symbol)
            if price is not None:
                state["price"] = price
            return state
        except Exception as exc:
            logger.warning(f"[market data] ccxt fallback to REST: {exc}")
            return get_btc_market_state(symbol)

    def get_price(self, symbol: str = DEFAULT_SYMBOL) -> float | None:
        state = self.get_market_state(symbol.replace("/", ""))
        price = state.get("price")
        return float(price) if price is not None else None
