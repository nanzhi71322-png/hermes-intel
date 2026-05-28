from pathlib import Path


root = Path(__file__).resolve().parents[1]
tg_bot_path = root / "tg_bot.py"
tg_bot_text = tg_bot_path.read_text(encoding="utf-8")


def assert_contains(text, needle, message):
    assert needle in text, message


assert_contains(
    tg_bot_text,
    'TELEGRAM_NOTIFY_MODE = os.getenv("TELEGRAM_NOTIFY_MODE", "trade_only").lower()',
    "TELEGRAM_NOTIFY_MODE must default to trade_only",
)
assert_contains(
    tg_bot_text,
    "def should_send_analysis_message():",
    "should_send_analysis_message function is required",
)
assert_contains(
    tg_bot_text,
    '    return TELEGRAM_NOTIFY_MODE == "all"',
    "should_send_analysis_message must only allow all-mode analysis sends",
)
assert_contains(
    tg_bot_text,
    "from notifications.trade_notifications import send_trade_opened_notification",
    "tg_bot.py must import send_trade_opened_notification",
)

assert tg_bot_text.count("await send_trade_opened_notification(") == 2, (
    "expected exactly two trade-open helper calls"
)
assert tg_bot_text.count("Hermes paper trade opened") == 0, (
    "tg_bot.py must not contain inline trade-open message formatting"
)


def opened_position_block(marker):
    marker_index = tg_bot_text.find(marker)
    assert marker_index != -1, f"missing {marker}"

    block_start = tg_bot_text.rfind("if opened_position:", 0, marker_index)
    assert block_start != -1, f"missing opened_position block before {marker}"

    send_line = "await send_trade_opened_notification("
    send_index = tg_bot_text.find(send_line, marker_index)
    assert send_index != -1, f"missing helper send after {marker}"

    block_end = tg_bot_text.find("                    else:", send_index)
    assert block_end != -1, f"missing opened_position block end after {marker}"

    return tg_bot_text[block_start:block_end]


def assert_call_sequence(block, expected_symbol):
    required_tokens = [
        "await send_trade_opened_notification(",
        "app.bot,",
        "chat_id,",
        "decision,",
        f"{expected_symbol},",
        "opened_position,",
        "underlying_asset,",
        "market_state,",
        "direction_adjustment,",
        "logger,",
    ]

    cursor = -1
    for token in required_tokens:
        next_index = block.find(token, cursor + 1)
        assert next_index != -1, f"helper call missing or misordered token {token}"
        cursor = next_index


keyword_block = opened_position_block("mark_trade_opened(keyword)")
name_block = opened_position_block("mark_trade_opened(name)")

for marker, block in [
    ("mark_trade_opened(keyword)", keyword_block),
    ("mark_trade_opened(name)", name_block),
]:
    mark_index = block.find(marker)
    send_index = block.find("await send_trade_opened_notification(")
    assert mark_index != -1, f"missing {marker}"
    assert send_index != -1, f"missing helper send after {marker}"
    assert mark_index < send_index, f"{marker} must happen before helper send"

assert_call_sequence(keyword_block, "keyword")
assert_call_sequence(name_block, "name")

assert tg_bot_text.count("if should_send_analysis_message():") >= 2, (
    "normal analysis sends must remain gated by should_send_analysis_message()"
)

print("P2.13b-2 trade notification wiring contract checks passed")
