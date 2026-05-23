import asyncio
import ast
import inspect
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

helper_path = root / "notifications" / "trade_notifications.py"
helper_bytes = helper_path.read_bytes()
assert not helper_bytes.startswith(b"\xef\xbb\xbf"), "helper file must not contain BOM"
helper_text = helper_bytes.decode("utf-8")

from notifications.trade_notifications import (  # noqa: E402
    build_trade_opened_message,
    send_trade_opened_notification,
)


def assert_contains(text, needle, message):
    assert needle in text, message


tree = ast.parse(helper_text)
top_level_functions = [
    node.name
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
assert top_level_functions == [
    "build_trade_opened_message",
    "send_trade_opened_notification",
], "helper must contain exactly the two expected top-level functions"

required_source_markers = [
    "direction_adjustment = direction_adjustment or {}",
    'action = str(decision.get("action", "")).upper()',
    "return (",
    'f"action: {action}\\n"',
    'f"symbol: {symbol}\\n"',
    'f"underlying: {opened_position.get(\'underlying_asset\') or underlying_asset}\\n"',
    'f"entry: {opened_position.get(\'entry_price\')}\\n"',
    'f"size: {opened_position.get(\'size\')}\\n"',
    'f"confidence: {decision.get(\'confidence\')}\\n"',
    'f"bias: {market_state.get(\'market_bias\')}\\n"',
    'f"score: {market_state.get(\'score\')}\\n"',
    'f"cc: {market_state.get(\'confirmation_count\')}\\n"',
    'f"breakout: {market_state.get(\'breakout\')}\\n"',
    'f"bb: {market_state.get(\'bb_position\')}\\n"',
    'f"reason: {direction_adjustment.get(\'reason\')}"',
    "await bot.send_message(",
    "chat_id=chat_id,",
    "text=build_trade_opened_message(",
    "except Exception as notify_error:",
    "[telegram notify error] trade_opened",
]

for marker in required_source_markers:
    assert_contains(helper_text, marker, f"helper source missing {marker}")

signature = inspect.signature(send_trade_opened_notification)
assert list(signature.parameters) == [
    "bot",
    "chat_id",
    "decision",
    "symbol",
    "opened_position",
    "underlying_asset",
    "market_state",
    "direction_adjustment",
    "logger",
], "send_trade_opened_notification signature changed"

message = build_trade_opened_message(
    {"action": "short", "confidence": 80},
    "btc",
    {"underlying_asset": "BTCUSDT", "entry_price": 77077.03, "size": 10},
    "BTCUSDT",
    {
        "market_bias": "bearish",
        "score": 85,
        "confirmation_count": 3,
        "breakout": "down",
        "bb_position": "outside_lower",
    },
    {"reason": "strong bearish market_state promotes watch to short"},
)

required_lines = [
    "action: SHORT",
    "symbol: btc",
    "underlying: BTCUSDT",
    "entry: 77077.03",
    "size: 10",
    "confidence: 80",
    "bias: bearish",
    "score: 85",
    "cc: 3",
    "breakout: down",
    "bb: outside_lower",
    "reason: strong bearish market_state promotes watch to short",
]

for line in required_lines:
    assert line in message, f"helper message missing {line}"

none_reason_message = build_trade_opened_message(
    {"action": "long"},
    "btc",
    {"underlying_asset": "BTCUSDT", "entry_price": 77077.03, "size": 3},
    "BTCUSDT",
    {"market_bias": "bullish"},
    None,
)
assert "action: LONG" in none_reason_message
assert "reason: None" in none_reason_message


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append({"chat_id": chat_id, "text": text})


class FailingBot:
    async def send_message(self, chat_id, text):
        raise RuntimeError("boom")


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


async def run_async_contract_checks():
    bot = FakeBot()
    logger = FakeLogger()

    await send_trade_opened_notification(
        bot,
        8414455056,
        {"action": "short", "confidence": 80},
        "btc",
        {"underlying_asset": "BTCUSDT", "entry_price": 77077.03, "size": 10},
        "BTCUSDT",
        {
            "market_bias": "bearish",
            "score": 85,
            "confirmation_count": 3,
            "breakout": "down",
            "bb_position": "outside_lower",
        },
        {"reason": "strong bearish market_state promotes watch to short"},
        logger,
    )

    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 8414455056
    sent_text = bot.messages[0]["text"]
    assert "Hermes paper trade opened" in sent_text
    assert "action: SHORT" in sent_text
    assert "underlying: BTCUSDT" in sent_text
    assert "entry: 77077.03" in sent_text

    failing_logger = FakeLogger()
    await send_trade_opened_notification(
        FailingBot(),
        8414455056,
        {"action": "short"},
        "btc",
        {"underlying_asset": "BTCUSDT", "entry_price": 77077.03, "size": 10},
        "BTCUSDT",
        {},
        None,
        failing_logger,
    )
    assert failing_logger.errors
    assert "[telegram notify error] trade_opened" in failing_logger.errors[0]


asyncio.run(run_async_contract_checks())

print("P2.13b-1 trade notification helper contract checks passed")
