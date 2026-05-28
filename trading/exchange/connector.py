"""CCXT 交易所连接封装。"""

from loguru import logger

from config.trading import (
    BINANCE_API_KEY,
    BINANCE_SECRET,
    EXCHANGE_ID,
    TRADING_TESTNET,
)


class ExchangeConnector:
    def __init__(
        self,
        exchange_id: str | None = None,
        api_key: str | None = None,
        secret: str | None = None,
        testnet: bool | None = None,
    ):
        self.exchange_id = exchange_id or EXCHANGE_ID
        self.api_key = api_key if api_key is not None else BINANCE_API_KEY
        self.secret = secret if secret is not None else BINANCE_SECRET
        self.testnet = TRADING_TESTNET if testnet is None else testnet
        self._exchange = None

    def _ensure_exchange(self):
        if self._exchange is not None:
            return self._exchange

        import ccxt

        exchange_class = getattr(ccxt, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"unsupported exchange: {self.exchange_id}")

        config = {
            "apiKey": self.api_key,
            "secret": self.secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        self._exchange = exchange_class(config)

        if self.testnet and hasattr(self._exchange, "set_sandbox_mode"):
            self._exchange.set_sandbox_mode(True)

        logger.info(
            f"[exchange] initialized id={self.exchange_id} testnet={self.testnet}"
        )
        return self._exchange

    def fetch_ticker(self, symbol: str) -> dict:
        exchange = self._ensure_exchange()
        ticker = exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last": ticker.get("last"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "timestamp": ticker.get("timestamp"),
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 60) -> list:
        exchange = self._ensure_exchange()
        return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_order_book(self, symbol: str, limit: int = 50) -> dict:
        exchange = self._ensure_exchange()
        return exchange.fetch_order_book(symbol, limit=limit)

    def fetch_balance(self) -> dict:
        exchange = self._ensure_exchange()
        return exchange.fetch_balance()

    def create_market_order(self, symbol: str, side: str, amount: float) -> dict:
        exchange = self._ensure_exchange()
        return exchange.create_order(symbol, "market", side, amount)

    def close(self) -> None:
        if self._exchange is not None:
            close_fn = getattr(self._exchange, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception as exc:
                    logger.warning(f"[exchange] close error: {exc}")
            self._exchange = None
