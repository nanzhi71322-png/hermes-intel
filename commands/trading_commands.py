"""Telegram 交易相关命令。"""
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from config.trading import DEFAULT_SYMBOL, TRADING_PAUSED, is_live_mode
from trading.execution.live import LiveExecutor
from trading.status import build_trade_status_text_async

_test_size_usd = 15.0


async def tradereport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from trading.report import build_tradereport_text_async

    text = await build_tradereport_text_async()
    await update.message.reply_text(text[:4000])


async def tradestatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await build_trade_status_text_async()
    await update.message.reply_text(text[:4000])


async def tradetest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_live_mode():
        await update.message.reply_text("tradetest only available in TRADING_MODE=live")
        return

    if TRADING_PAUSED:
        await update.message.reply_text("trading is paused (TRADING_PAUSED=true)")
        return

    await update.message.reply_text(
        f"placing testnet market buy ${_test_size_usd} {DEFAULT_SYMBOL}..."
    )

    def _run_test():
        from trading.exchange.connector import ExchangeConnector

        connector = ExchangeConnector()
        try:
            ticker = connector.fetch_ticker(DEFAULT_SYMBOL)
            price = ticker.get("last")
            if not price:
                return {"ok": False, "error": "no price"}

            executor = LiveExecutor(connector=connector)
            decision = {"action": "long", "confidence": 99}
            position = executor.open_position(
                decision,
                float(price),
                "btc",
                _test_size_usd,
                metadata={"source": "tradetest"},
            )
            if not position:
                return {"ok": False, "error": "open_position returned None"}
            return {
                "ok": True,
                "order_id": position.get("order_id"),
                "price": price,
                "size": _test_size_usd,
                "symbol": DEFAULT_SYMBOL,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            connector.close()

    result = await asyncio.to_thread(_run_test)
    if result.get("ok"):
        await update.message.reply_text(
            "Testnet LIVE order OK\n"
            f"symbol: {result.get('symbol')}\n"
            f"size: ${result.get('size')}\n"
            f"price: {result.get('price')}\n"
            f"order_id: {result.get('order_id')}"
        )
        return

    await update.message.reply_text(f"tradetest failed: {result.get('error')}")


async def tradepause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "TRADING_PAUSED is env-controlled.\n"
        "Set TRADING_PAUSED=true in /opt/hermes/.env and restart hermes-bot.\n"
        "Or use: /tradestatus to check current state."
    )


async def traderesume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Set TRADING_PAUSED=false in /opt/hermes/.env and restart hermes-bot."
    )


async def tradereport_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from trading.daily_report import send_daily_report_now

    await send_daily_report_now(context.bot)
    await update.message.reply_text("中文报表已发送")
