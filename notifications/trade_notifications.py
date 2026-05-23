def build_trade_opened_message(
    decision,
    symbol,
    opened_position,
    underlying_asset,
    market_state,
    direction_adjustment,
):
    decision = decision or {}
    opened_position = opened_position or {}
    market_state = market_state or {}
    direction_adjustment = direction_adjustment or {}

    action = str(decision.get("action", "")).upper()

    return (
        "\U0001F680 Hermes paper trade opened\n"
        f"action: {action}\n"
        f"symbol: {symbol}\n"
        f"underlying: {opened_position.get('underlying_asset') or underlying_asset}\n"
        f"entry: {opened_position.get('entry_price')}\n"
        f"size: {opened_position.get('size')}\n"
        f"confidence: {decision.get('confidence')}\n"
        f"bias: {market_state.get('market_bias')}\n"
        f"score: {market_state.get('score')}\n"
        f"cc: {market_state.get('confirmation_count')}\n"
        f"breakout: {market_state.get('breakout')}\n"
        f"bb: {market_state.get('bb_position')}\n"
        f"reason: {direction_adjustment.get('reason')}"
    )


async def send_trade_opened_notification(
    bot,
    chat_id,
    decision,
    symbol,
    opened_position,
    underlying_asset,
    market_state,
    direction_adjustment,
    logger,
):
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=build_trade_opened_message(
                decision,
                symbol,
                opened_position,
                underlying_asset,
                market_state,
                direction_adjustment,
            ),
        )
    except Exception as notify_error:
        logger.error(f"[telegram notify error] trade_opened {notify_error}")
