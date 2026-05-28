"""Live 执行器：CCXT Spot 下单（Testnet/Mainnet）。"""

from datetime import datetime

from loguru import logger

from config.trading import MAX_OPEN_POSITIONS
from trading.exchange.connector import ExchangeConnector
from trading.exchange.order_utils import normalize_market_buy
from trading.exchange.symbols import resolve_ccxt_symbol, resolve_underlying_asset
from trading.execution.base import BaseExecutor
from trading.execution.exit_rules import should_close_position
from trading.storage.live_portfolio import (
    append_closed_record,
    append_order_record,
    append_position,
    load_positions,
    update_position,
)


class LiveExecutor(BaseExecutor):
    mode = "live"

    def __init__(self, connector: ExchangeConnector | None = None):
        self.connector = connector or ExchangeConnector()
        self._positions = load_positions()

    def open_position(self, decision, price, symbol, size_usd, metadata=None):
        action = decision.get("action")
        if action not in ("long", "short"):
            return None

        if action == "short":
            logger.info("[live executor] spot short blocked")
            return None

        ccxt_symbol = resolve_ccxt_symbol(symbol)
        if not price or price <= 0:
            return None

        try:
            amount, notional = normalize_market_buy(
                self.connector._ensure_exchange(),
                ccxt_symbol,
                float(size_usd),
                float(price),
            )
        except Exception as exc:
            logger.error(f"[live executor] order normalize failed: {exc}")
            return None

        if amount <= 0:
            return None

        self._positions = load_positions()
        if len(self._positions) >= MAX_OPEN_POSITIONS:
            logger.info("[live executor] max open positions reached")
            return None

        try:
            order = self.connector.create_market_order(ccxt_symbol, "buy", amount)
        except Exception as exc:
            logger.error(f"[live executor] order failed: {exc}")
            append_order_record(
                {
                    "status": "failed",
                    "side": "buy",
                    "symbol": ccxt_symbol,
                    "size_usd": size_usd,
                    "amount": amount,
                    "error": str(exc),
                }
            )
            return None

        underlying = resolve_underlying_asset(symbol)
        position = {
            "entry_price": float(price),
            "type": action,
            "size": float(notional),
            "amount": float(amount),
            "symbol": symbol,
            "underlying_asset": underlying,
            "metadata": metadata or {},
            "order_id": order.get("id"),
            "exchange_symbol": ccxt_symbol,
            "mode": "live",
            "status": "open",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._positions.append(position)
        append_position(position)
        append_order_record(
            {
                "status": "filled",
                "side": "buy",
                "symbol": ccxt_symbol,
                "size_usd": notional,
                "amount": amount,
                "order_id": order.get("id"),
                "entry_price": float(price),
            }
        )
        logger.info(f"[live executor] opened {action} {ccxt_symbol} size={notional:.2f}")
        return position

    def update_positions(self, current_price, symbol):
        self._positions = load_positions()
        if not current_price:
            return {"balance": None, "open_positions": len(self._positions)}

        for position in list(self._positions):
            ccxt_symbol = position.get("exchange_symbol") or resolve_ccxt_symbol(symbol)
            exit_check = should_close_position(position, float(current_price))
            if not exit_check["close"]:
                continue

            still_open = self._close_position(position, ccxt_symbol, current_price, exit_check)
            if still_open is not None:
                logger.info(f"[live executor] close deferred for {ccxt_symbol}")

        self._positions = load_positions()
        logger.info(f"[live portfolio] open_positions: {len(self._positions)}")
        return {"balance": None, "open_positions": len(self._positions)}

    def _close_position(self, position, ccxt_symbol, current_price, exit_check) -> dict | None:
        """成功平仓返回 None；失败返回原 position。"""
        amount = float(position.get("amount", 0))
        if amount <= 0 and position.get("size") and current_price:
            amount = float(position["size"]) / float(current_price)

        if amount <= 0:
            logger.warning("[live executor] close skipped: no amount")
            return position

        try:
            exchange = self.connector._ensure_exchange()
            exchange.load_markets()
            amount = float(exchange.amount_to_precision(ccxt_symbol, amount))
            order = self.connector.create_market_order(ccxt_symbol, "sell", amount)
        except Exception as exc:
            logger.error(f"[live executor] close failed: {exc}")
            append_order_record(
                {
                    "status": "close_failed",
                    "side": "sell",
                    "symbol": ccxt_symbol,
                    "amount": amount,
                    "error": str(exc),
                    "reason": exit_check.get("reason"),
                }
            )
            return position

        pnl_pct = exit_check.get("pnl_pct", 0.0)
        pnl = float(position.get("size", 0)) * float(pnl_pct)
        position["status"] = "closed"
        position["closed_at"] = datetime.utcnow().isoformat()
        position["exit_price"] = float(current_price)
        position["exit_reason"] = exit_check.get("reason")
        position["pnl"] = pnl
        position["pnl_pct"] = pnl_pct
        position["close_order_id"] = order.get("id")
        update_position(position)

        append_order_record(
            {
                "status": "closed",
                "side": "sell",
                "symbol": ccxt_symbol,
                "amount": amount,
                "order_id": order.get("id"),
                "exit_price": float(current_price),
                "reason": exit_check.get("reason"),
                "pnl": pnl,
            }
        )
        append_closed_record(
            {
                "symbol": ccxt_symbol,
                "entry_price": position.get("entry_price"),
                "exit_price": float(current_price),
                "size": position.get("size"),
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "reason": exit_check.get("reason"),
                "open_order_id": position.get("order_id"),
                "close_order_id": order.get("id"),
            }
        )
        logger.info(
            f"[live executor] closed {ccxt_symbol} reason={exit_check.get('reason')} "
            f"pnl={pnl:.4f} pnl_pct={pnl_pct:.4f}"
        )
        return None

    def has_open_exposure(self, underlying_asset, action) -> bool:
        self._positions = load_positions()
        target = resolve_underlying_asset(underlying_asset)
        for position in self._positions:
            pos_underlying = resolve_underlying_asset(
                position.get("underlying_asset") or position.get("symbol")
            )
            if pos_underlying != target:
                continue
            if position.get("type") != action:
                continue
            return True
        return False
