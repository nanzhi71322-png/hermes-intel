"""统一交易链：从 tg_bot.py 抽出的过滤 + 执行逻辑。"""

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from config.trading import MAX_BTC_PRICE, MIN_BTC_PRICE
from intel.market_confirmation import confirm_market_trade
from intel.market_core import confirm_market_core
from intel.market_candidate_tracker import (
    evaluate_market_candidates,
    get_best_market_candidate_edge,
    get_market_candidate_stats,
)
from intel.market_state import confirm_long_quality_for_execution, confirm_market_state_for_execution
from intel.opportunity_engine import mark_trade_opened
from config.trading import TRADING_PAUSED
from pipeline.context import TradePipelineContext, TradePipelineResult
from trading.risk.manager import RiskManager


def _trade_size_for_confidence(confidence: int) -> float | None:
    if confidence >= 80:
        return 10.0
    if confidence >= 70:
        return 3.0
    return None


def _build_metadata(ctx: TradePipelineContext) -> dict:
    return {
        "confidence": ctx.decision["confidence"],
        "alpha_score": ctx.alpha["alpha_score"],
        "signal_score": ctx.signal["score"],
        "narrative": ctx.narrative["narrative"],
        "action": ctx.decision["action"],
        "original_action": ctx.direction_adjustment["original_action"],
        "direction_adjust_reason": ctx.direction_adjustment["reason"],
        "underlying_asset": ctx.underlying_asset,
        "market_bias": ctx.market_state.get("market_bias"),
        "market_score": ctx.market_state.get("score"),
        "orderbook_imbalance": ctx.market_state.get("orderbook_imbalance"),
        "volume_ratio_1m": ctx.market_state.get("volume_ratio_1m"),
        "bb_position": ctx.market_state.get("bb_position"),
        "breakout": ctx.market_state.get("breakout"),
        "bullish_count": ctx.market_state.get("bullish_count"),
        "bearish_count": ctx.market_state.get("bearish_count"),
        "confirmation_count": ctx.market_state.get("confirmation_count"),
        "bullish_reasons": ctx.market_state.get("bullish_reasons"),
        "bearish_reasons": ctx.market_state.get("bearish_reasons"),
        "market_candidate_action": ctx.market_candidate.get("action"),
        "market_candidate_confidence": ctx.market_candidate.get("confidence"),
        "market_candidate_reason": ctx.market_candidate.get("reason"),
    }


def run_trade_pipeline(
    ctx: TradePipelineContext,
    executor,
    risk_manager: RiskManager | None = None,
) -> TradePipelineResult:
    risk_manager = risk_manager or RiskManager()
    source_key = ctx.source_key
    decision = ctx.decision
    market_price = ctx.market_price
    previous_price = ctx.previous_price
    market_state = ctx.market_state
    result = TradePipelineResult(last_trade_action=ctx.last_trade_action)

    if TRADING_PAUSED:
        logger.info(
            f"[trade chain] stage=blocked_by_trading_paused symbol={source_key}"
        )
        post_trade_cycle(executor, market_price, source_key)
        return result

    if market_price is None or not (MIN_BTC_PRICE <= market_price <= MAX_BTC_PRICE):
        logger.info(
            f"[trade chain] stage=blocked_by_invalid_price "
            f"symbol={source_key} price={market_price}"
        )
        logger.info("invalid price, skip trading")
        return result

    if decision["action"] not in ("long", "short"):
        logger.info(
            f"[trade chain] stage=blocked_by_non_tradeable_action "
            f"action={decision['action']} symbol={source_key}"
        )
        logger.info(f"[trade skip] action={decision['action']} reason=not tradeable")
        post_trade_cycle(executor, market_price, source_key)
        return result

    trade_size = _trade_size_for_confidence(decision["confidence"])
    result.trade_size = trade_size

    if trade_size is None:
        logger.info(
            f"[trade chain] stage=blocked_by_confidence "
            f"action={decision['action']} confidence={decision['confidence']} "
            f"size={trade_size} symbol={source_key}"
        )
        post_trade_cycle(executor, market_price, source_key)
        return result

    allowed, risk_reason = risk_manager.check_open_allowed(decision, trade_size)
    if not allowed:
        logger.info(
            f"[trade chain] stage=blocked_by_risk "
            f"action={decision['action']} reason={risk_reason}"
        )
        post_trade_cycle(executor, market_price, source_key)
        return result

    logger.info(
        f"[trade sizing] confidence: {decision['confidence']} size: {trade_size}"
    )
    logger.info(
        f"[trade chain] stage=before_market_confirm "
        f"action={decision['action']} confidence={decision['confidence']} "
        f"size={trade_size} symbol={source_key} price={market_price}"
    )

    market_confirmation = confirm_market_trade(
        decision["action"],
        market_price,
        previous_price,
    )
    logger.info(
        f"[trade chain] stage=after_market_confirm "
        f"action={decision['action']} "
        f"confirmed={market_confirmation['confirmed']} "
        f"score={market_confirmation['market_score']} "
        f"reason={market_confirmation['reason']}"
    )
    logger.info(
        f"[market confirm] action={decision['action']} "
        f"confirmed={market_confirmation['confirmed']} "
        f"score={market_confirmation['market_score']} "
        f"reason={market_confirmation['reason']}"
    )

    duplicate_exposure_open = executor.has_open_exposure(
        ctx.underlying_asset,
        decision["action"],
    )
    logger.info(
        f"[trade chain] stage=duplicate_check "
        f"symbol={source_key} underlying_asset={ctx.underlying_asset} "
        f"action={decision['action']} "
        f"has_open_exposure={duplicate_exposure_open} "
        f"last_trade_action={ctx.last_trade_action}"
    )

    opened_position = None
    if duplicate_exposure_open:
        logger.info(
            f"[trade chain] stage=blocked_by_duplicate_trade "
            f"action={decision['action']} "
            f"reason=open_same_underlying_direction_exposure "
            f"underlying_asset={ctx.underlying_asset}"
        )
        logger.info(
            f"[trade filter] duplicate direction blocked: {decision['action']}"
        )
    elif market_confirmation["confirmed"]:
        state_confirm = confirm_market_state_for_execution(
            decision["action"],
            market_state,
        )
        logger.info(
            f"[trade chain] stage=after_market_state_execution_filter "
            f"action={decision['action']} "
            f"confirmed={state_confirm['confirmed']} "
            f"score={state_confirm['score']} "
            f"reason={state_confirm['reason']} "
            f"market_bias={market_state.get('market_bias')} "
            f"confirmation_count={market_state.get('confirmation_count')}"
        )
        if not state_confirm["confirmed"]:
            logger.info(
                f"[trade chain] stage=blocked_by_market_state "
                f"action={decision['action']} reason={state_confirm['reason']}"
            )
        else:
            long_quality = confirm_long_quality_for_execution(
                decision["action"],
                market_state,
            )
            logger.info(
                f"[trade chain] stage=after_long_quality_filter "
                f"action={decision['action']} "
                f"confirmed={long_quality['confirmed']} "
                f"score={long_quality['score']} "
                f"reason={long_quality['reason']} "
                f"market_bias={market_state.get('market_bias')} "
                f"confirmation_count={market_state.get('confirmation_count')} "
                f"breakout={market_state.get('breakout')} "
                f"bb_position={market_state.get('bb_position')}"
            )
            if not long_quality["confirmed"]:
                logger.info(
                    f"[trade chain] stage=blocked_by_long_quality "
                    f"action={decision['action']} reason={long_quality['reason']}"
                )
            else:
                price_snapshot = {
                    "current_price": market_price,
                    "previous_price": previous_price,
                }
                logger.info(
                    f"[trade chain] stage=before_market_core "
                    f"action={decision['action']} price={market_price} "
                    f"previous_price={previous_price}"
                )
                core_confirm = confirm_market_core(decision["action"], price_snapshot)
                logger.info(
                    f"[trade chain] stage=after_market_core "
                    f"action={decision['action']} "
                    f"confirmed={core_confirm['confirmed']} "
                    f"score={core_confirm['score']} reason={core_confirm['reason']}"
                )
                logger.info(
                    f"[market core] action={decision['action']} "
                    f"confirmed={core_confirm['confirmed']} "
                    f"score={core_confirm['score']} reason={core_confirm['reason']}"
                )
                if not core_confirm["confirmed"]:
                    logger.info(
                        f"[trade chain] stage=blocked_by_market_core "
                        f"action={decision['action']} reason={core_confirm['reason']}"
                    )
                    result.skip_signal_send = True
                    return result

                stage_label = "execute_trade"
                logger.info(
                    f"[trade chain] stage=before_{stage_label} "
                    f"action={decision['action']} size={trade_size} "
                    f"price={market_price} confidence={decision['confidence']} "
                    f"mode={executor.mode}"
                )
                opened_position = executor.open_position(
                    decision,
                    market_price,
                    source_key,
                    trade_size,
                    metadata=_build_metadata(ctx),
                )
                logger.info(
                    f"[trade chain] stage=after_{stage_label} "
                    f"action={decision['action']} result={opened_position}"
                )
    else:
        logger.info(
            f"[trade chain] stage=blocked_by_market_confirm "
            f"action={decision['action']} "
            f"reason={market_confirmation['reason']}"
        )

    if opened_position:
        result.last_trade_action = decision["action"]
        logger.info(
            f"[trade opened] action: {decision['action']} "
            f"confidence: {decision['confidence']} "
            f"alpha: {ctx.alpha['alpha_score']} mode={executor.mode}"
        )
        mark_trade_opened(source_key)

    result.opened_position = opened_position
    post_trade_cycle(executor, market_price, source_key)
    return result


def post_trade_cycle(executor, market_price, source_key: str) -> None:
    executor.update_positions(market_price, source_key)
    candidate_events = evaluate_market_candidates(
        datetime.utcnow().isoformat(),
        "BTCUSDT",
        market_price,
    )
    for event in candidate_events:
        logger.info(
            f"[market candidate result] horizon={event['horizon']} "
            f"action={event['action']} win={event['win']} "
            f"pnl_pct={event['pnl_pct']:.6f} "
            f"entry={event['entry_price']} current={event['current_price']} "
            f"confidence={event['confidence']} bias={event['market_bias']} "
            f"score={event['market_score']} reason={event['reason']}"
        )
        stats = get_market_candidate_stats()
        event_stats = stats.get(event["horizon"], {}).get(event["action"], {})
        logger.info(
            f"[market candidate stats] horizon={event['horizon']} "
            f"action={event['action']} count={event_stats.get('count', 0)} "
            f"wins={event_stats.get('wins', 0)} "
            f"losses={event_stats.get('losses', 0)} "
            f"win_rate={event_stats.get('win_rate', 0):.4f} "
            f"avg_pnl_pct={event_stats.get('avg_pnl_pct', 0):.6f}"
        )
        edge = get_best_market_candidate_edge()
        logger.info(
            f"[market candidate edge] horizon={edge['horizon']} "
            f"action={edge['action']} count={edge['count']} "
            f"win_rate={edge['win_rate']:.4f} "
            f"avg_pnl_pct={edge['avg_pnl_pct']:.6f} "
            f"estimated_cost_pct={edge['estimated_cost_pct']:.6f} "
            f"net_avg_pnl_pct={edge['net_avg_pnl_pct']:.6f} "
            f"edge_score={edge['edge_score']:.8f} reason={edge['reason']}"
        )
