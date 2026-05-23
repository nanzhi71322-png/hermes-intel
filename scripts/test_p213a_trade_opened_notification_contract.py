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

assert tg_bot_text.count("Hermes paper trade opened") == 2, (
    "expected exactly two trade-open Telegram notification blocks"
)
assert tg_bot_text.count("[telegram notify error] trade_opened") == 2, (
    "expected exactly two trade-open notification error handlers"
)


def opened_position_block(marker):
    marker_index = tg_bot_text.find(marker)
    assert marker_index != -1, f"missing {marker}"

    block_start = tg_bot_text.rfind("if opened_position:", 0, marker_index)
    assert block_start != -1, f"missing opened_position block before {marker}"

    error_line = 'logger.error(f"[telegram notify error] trade_opened {notify_error}")'
    block_end = tg_bot_text.find(error_line, marker_index)
    assert block_end != -1, f"missing notification error log after {marker}"
    block_end += len(error_line)

    return tg_bot_text[block_start:block_end]


keyword_block = opened_position_block("mark_trade_opened(keyword)")
name_block = opened_position_block("mark_trade_opened(name)")
notification_blocks = [keyword_block, name_block]

required_fields = [
    "action:",
    "symbol:",
    "underlying:",
    "entry:",
    "underlying:",
    "entry:",
    "size:",
    "confidence:",
    "bias:",
    "score:",
    "cc:",
    "breakout:",
    "bb:",
    "reason:",
]

for block in notification_blocks:
    for field in required_fields:
        assert field in block, f"trade-open notification missing field {field}"

for marker, block in [
    ("mark_trade_opened(keyword)", keyword_block),
    ("mark_trade_opened(name)", name_block),
]:
    mark_index = block.find(marker)
    send_index = block.find("await app.bot.send_message")
    assert mark_index != -1, f"missing {marker}"
    assert send_index != -1, f"missing Telegram send after {marker}"
    assert mark_index < send_index, f"{marker} must happen before Telegram send"

for block in notification_blocks:
    assert "try:" in block, "trade-open Telegram send must be inside try"
    assert "await app.bot.send_message" in block, "trade-open Telegram send missing"
    assert "except Exception as notify_error:" in block, (
        "trade-open Telegram send must isolate failures"
    )
    assert (
        'logger.error(f"[telegram notify error] trade_opened {notify_error}")'
        in block
    ), "trade-open notification failure must be logged"

assert tg_bot_text.count("if should_send_analysis_message():") >= 2, (
    "normal analysis sends must remain gated by should_send_analysis_message()"
)

print("P2.13a trade opened notification contract checks passed")
