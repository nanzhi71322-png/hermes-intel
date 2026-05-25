import asyncio
import json
import os

from datetime import datetime

from loguru import logger

from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop, TypeHandler

import browser.manager as browser_manager
from browser.manager import (
    browser_open,
    init_browser,
    reset_agent_browser,
)
from commands import register_handlers
from config.clients import llm_client as client
from config.settings import (
    ALLOWED_CHAT_IDS,
    BOT_TOKEN,
    DEEPSEEK_MODEL,
    TASKS_FILE,
    ensure_runtime_dirs,
)
from intel.alpha_engine import compute_alpha, detect_narrative, detect_whale_activity
from intel.feedback_engine import evaluate_decisions, extract_price_from_text, record_decision
from intel.market_candidate_tracker import record_market_candidate
from intel.market_price import get_btc_price
from intel.market_state import build_market_candidate, get_btc_market_state
from intel.opportunity_engine import adjust_decision_for_market_direction, generate_decision
from intel.signal_engine import score_signal
from memory.signals import filter_new_signals
from notifications.trade_notifications import send_trade_opened_notification
from pipeline.context import TradePipelineContext
from pipeline.trade_pipeline import run_trade_pipeline
from trading.factory import get_executor
from trading.risk.manager import RiskManager
from trading.daily_report import daily_report_loop
from utils.logging import setup_logging
from utils.urls import build_x_search_url

ensure_runtime_dirs()
setup_logging()

autonomous_tasks = {}
DEBUG_BYPASS_SIGNAL_FILTER = os.getenv(
    "DEBUG_BYPASS_SIGNAL_FILTER",
    "false"
).lower() == "true"
TELEGRAM_NOTIFY_MODE = os.getenv("TELEGRAM_NOTIFY_MODE", "trade_only").lower()
previous_market_prices = {}
last_trade_action = None
trade_executor = get_executor()
trade_risk_manager = RiskManager()

AGENT_PROFILES = {
    "btc": {
        "keyword": "bitcoin",
        "role": "BTC market sentiment and macro narrative analyst",
        "focus": "bitcoin price sentiment, whale movement, macro narratives, ETF/institutional activity, bull/bear traps"
    },
    "eth": {
        "keyword": "ethereum",
        "role": "ETH ecosystem and DeFi sentiment analyst",
        "focus": "ETH price sentiment, staking, L2, DeFi, Ethereum upgrades, institutional flows"
    },
    "sol": {
        "keyword": "solana",
        "role": "Solana ecosystem intelligence analyst",
        "focus": "SOL price sentiment, meme coins, ecosystem launches, outages, scam tokens, volume spikes"
    },
    "scam": {
        "keyword": "crypto wallet drainer OR rug pull OR fake airdrop OR phishing crypto",
        "role": "crypto scam and phishing detection analyst",
        "focus": "wallet drainers, fake airdrops, phishing domains, rug pulls, fake token launches, suspicious KOL promotions, wallet connection scams"
    },
    "breaking": {
        "keyword": "crypto breaking news",
        "role": "breaking crypto news analyst",
        "focus": "urgent news, exchange issues, hacks, regulation, ETF, liquidation cascades, major announcements"
    }
}


def should_send_analysis_message():
    return TELEGRAM_NOTIFY_MODE == "all"


async def process_trade_cycle(
    source_key,
    chat_id,
    decision,
    market_price,
    price_snapshot,
    market_state,
    market_candidate,
    direction_adjustment,
    signal,
    alpha,
    narrative,
):
    global last_trade_action

    if market_price is None or not (30000 <= market_price <= 150000):
        logger.info(
            f"[trade chain] stage=blocked_by_invalid_price "
            f"symbol={source_key} price={market_price}"
        )
        logger.info("invalid price, skip trading")
        return False

    previous_market_prices[source_key] = market_price
    trade_ctx = TradePipelineContext(
        source_key=source_key,
        decision=decision,
        market_price=market_price,
        previous_price=price_snapshot.get("previous_price"),
        market_state=market_state,
        market_candidate=market_candidate,
        direction_adjustment=direction_adjustment,
        signal=signal,
        alpha=alpha,
        narrative=narrative,
        underlying_asset="BTCUSDT",
        last_trade_action=last_trade_action,
    )
    trade_result = run_trade_pipeline(
        trade_ctx,
        trade_executor,
        trade_risk_manager,
    )

    if trade_result.skip_signal_send:
        return True

    if trade_result.opened_position:
        last_trade_action = trade_result.last_trade_action
        await send_trade_opened_notification(
            app.bot,
            chat_id,
            decision,
            source_key,
            trade_result.opened_position,
            trade_ctx.underlying_asset,
            market_state,
            direction_adjustment,
            logger,
            trading_mode=trade_executor.mode,
        )

    return False


def is_bad_x_page(text):
    normalized = (text or "").lower()

    if not normalized.strip():
        return True

    if "something went wrong" in normalized:
        return True

    if "sign in to x" in normalized:
        return True

    if "rate limited" in normalized:
        return True

    if "search timeline" in normalized:
        return False

    if "nitter" in normalized and "@" in normalized:
        return False

    if "replying to" in normalized and "@" in normalized:
        return False

    return True


def is_allowed(update):
    chat = update.effective_chat
    return bool(chat and chat.id in ALLOWED_CHAT_IDS)


async def access_control(update, context):
    if is_allowed(update):
        return

    if update.effective_message:
        await update.effective_message.reply_text("unauthorized")

    raise ApplicationHandlerStop


def save_autonomous_tasks():
    data = []

    for key in autonomous_tasks.keys():
        try:
            chat_id, keyword = key.split(":", 1)

            data.append({
                "chat_id": int(chat_id),
                "keyword": keyword
            })

        except Exception:
            pass

    try:
        with open(TASKS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"save task error: {e}")


async def restore_autonomous_tasks(application):
    global autonomous_tasks

    try:
        with open(TASKS_FILE, "r") as f:
            data = json.load(f)

    except Exception:
        data = []

    for item in data:
        try:
            chat_id = item["chat_id"]
            keyword = item["keyword"]

            key = f"{chat_id}:{keyword}"

            if key in autonomous_tasks:
                continue

            if keyword.startswith("agent:"):
                name = keyword.split(":", 1)[1]
                task = application.create_task(
                    agent_loop(chat_id, name)
                )
                key = f"{chat_id}:agent:{name}"
            else:
                task = application.create_task(
                    autonomous_loop(chat_id, keyword)
                )
                key = f"{chat_id}:{keyword}"

            autonomous_tasks[key] = task

            logger.info(f"[restore] scheduled autonomous: {key}")
            logger.info(f"restored autonomous: {key}")

        except Exception as e:
            logger.error(f"restore task error: {e}")


async def reset_shared_browser():
    async with browser_manager.browser_lock:
        context = browser_manager.browser_context
        browser_manager.browser_context = None
        browser_manager.browser_page = None

        if context:
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"shared browser reset error: {e}")


async def read_autonomous_browser_body(keyword, url):
    logger.info(f"[agent browser] opening: {keyword}")

    async with browser_manager.browser_lock:
        await browser_open(url)

        await browser_manager.browser_page.wait_for_timeout(3000)

        await browser_manager.browser_page.mouse.wheel(0, 1200)

        await browser_manager.browser_page.wait_for_timeout(2000)

        body = await browser_manager.browser_page.locator("body").inner_text(timeout=8000)

    logger.info(f"[agent browser] body read: {keyword} len={len(body)}")

    return body


async def read_agent_browser_body(name, url):
    logger.info(f"[agent browser] opening: {name}")

    async with browser_manager.browser_lock:
        await init_browser()

        await browser_manager.browser_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await browser_manager.browser_page.wait_for_timeout(3000)

        for _ in range(3):
            await browser_manager.browser_page.mouse.wheel(0, 1200)
            await browser_manager.browser_page.wait_for_timeout(1500)

        body = await browser_manager.browser_page.locator("body").inner_text(timeout=10000)

    logger.info(f"[agent browser] body read: {name} len={len(body)}")

    return body


async def autonomous_loop(chat_id, keyword):
    global last_trade_action

    while True:
        try:
            url = build_x_search_url(keyword)

            body = await asyncio.wait_for(
                read_autonomous_browser_body(keyword, url),
                timeout=45,
            )

            logger.info(f"[signal pipeline] raw body: {keyword} len={len(body)}")
            logger.info(f"[signal pipeline] quality check: {keyword}")
            if is_bad_x_page(body):
                logger.info("[x quality] bad page, skip analysis")
                await asyncio.sleep(300)
                continue

            raw_body = body
            logger.info(f"[signal pipeline] quality ok: {keyword}")
            logger.info(f"[signal pipeline] filtering: {keyword}")
            body = await asyncio.wait_for(
                asyncio.to_thread(filter_new_signals, keyword, body),
                timeout=20,
            )
            logger.info(f"[signal pipeline] filtered: {keyword} len={len(body)}")

            if not body:
                if DEBUG_BYPASS_SIGNAL_FILTER:
                    logger.info(f"[signal pipeline] debug bypass dedupe: {keyword}")
                    body = raw_body[:12000]
                else:
                    logger.info(f"[signal pipeline] no new signals: {keyword}")
                    await asyncio.sleep(300)
                    continue

            if not body:
                logger.info(f"[signal pipeline] no new signals: {keyword}")
                await asyncio.sleep(300)
                continue

            if len(body) > 12000:
                body = body[:12000]

            prompt = f"""
analyze this x search page.

focus:
- market sentiment
- bullish views
- bearish views
- important accounts
- scams
- unusual activity

content:
{body}
"""

            logger.info(f"[llm] starting analysis: {keyword}")
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.chat.completions.create,
                        model=DEEPSEEK_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "you are a crypto intelligence analyst"
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=0.2
                    ),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                logger.warning(f"[llm timeout] analysis timed out: {keyword}")
                await asyncio.sleep(300)
                continue
            except Exception as e:
                logger.error(f"[llm error] {keyword}: {e}")
                await asyncio.sleep(300)
                continue

            answer = response.choices[0].message.content
            logger.info(f"[llm] analysis received: {keyword} len={len(answer)}")

            if len(answer) > 4000:
                answer = answer[:4000]

            signal = score_signal(answer)
            signal_prefix = (
                f"[signal: {signal['level'].upper()} {signal['score']}] "
                f"{signal['reason']}"
            )
            whale = detect_whale_activity(answer)
            narrative = detect_narrative(answer)
            alpha = compute_alpha(signal, whale, narrative)
            alpha_prefix = (
                f"[alpha: {alpha['alpha_score']} | "
                f"whale: {'yes' if whale['whale'] else 'no'} | "
                f"narrative: {narrative['narrative']}]"
            )
            market_state = get_btc_market_state("BTCUSDT")
            market_price = market_state.get("price")
            if market_price is None:
                market_price = get_btc_price()
            logger.info(
                f"[market state] bias={market_state.get('market_bias')} "
                f"score={market_state.get('score')} "
                f"imbalance={market_state.get('orderbook_imbalance')} "
                f"volume_ratio={market_state.get('volume_ratio_1m')} "
                f"bb={market_state.get('bb_position')} "
                f"breakout={market_state.get('breakout')} "
                f"bull_count={market_state.get('bullish_count')} "
                f"bear_count={market_state.get('bearish_count')} "
                f"confirm_count={market_state.get('confirmation_count')} "
                f"bull_reasons={market_state.get('bullish_reasons')} "
                f"bear_reasons={market_state.get('bearish_reasons')} "
                f"reason={market_state.get('reason')}"
            )
            market_candidate = build_market_candidate(market_state)
            logger.info(
                f"[market candidate] action={market_candidate['action']} "
                f"confidence={market_candidate['confidence']} "
                f"reason={market_candidate['reason']}"
            )
            decision = generate_decision(
                signal,
                alpha,
                whale,
                narrative,
                answer,
                symbol=keyword,
                current_price=market_price,
            )
            price_snapshot = {
                "current_price": market_price,
                "previous_price": previous_market_prices.get(keyword),
            }
            direction_adjustment = adjust_decision_for_market_direction(
                decision,
                market_state,
                price_snapshot,
            )
            decision = direction_adjustment["decision"]
            logger.info(
                f"[decision direction] "
                f"original_action={direction_adjustment['original_action']} "
                f"final_action={direction_adjustment['final_action']} "
                f"changed={direction_adjustment['changed']} "
                f"reason={direction_adjustment['reason']} "
                f"market_bias={market_state.get('market_bias')} "
                f"market_score={market_state.get('score')} "
                f"confirmation_count={market_state.get('confirmation_count')} "
                f"current_price={price_snapshot.get('current_price')} "
                f"previous_price={price_snapshot.get('previous_price')}"
            )
            record_market_candidate(
                datetime.utcnow().isoformat(),
                "BTCUSDT",
                market_price,
                market_candidate,
                market_state,
                decision,
            )
            try:
                logger.info("[tg debug] sending analysis preview")
                debug_prefix = ""
                if decision["confidence"] < 70:
                    debug_prefix = "[DEBUG LOW SIGNAL]\n"

                if should_send_analysis_message():
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"{debug_prefix}{answer[:800]}"
                    )
            except Exception as e:
                logger.error(f"[tg debug error] {e}")

            price = extract_price_from_text(answer) or market_price
            record_decision(
                datetime.utcnow().isoformat(),
                {**decision, "narrative": narrative["narrative"]},
                price,
                keyword,
            )
            evaluate_decisions(market_price)
            if await process_trade_cycle(
                keyword,
                chat_id,
                decision,
                market_price,
                price_snapshot,
                market_state,
                market_candidate,
                direction_adjustment,
                signal,
                alpha,
                narrative,
            ):
                continue
            decision_prefix = (
                f"[decision: {decision['action'].upper()} | "
                f"confidence: {decision['confidence']} | "
                f"timeframe: {decision['timeframe']}]\n"
                f"reason: {decision['reason']}\n"
                f"risk: {decision['risk']}"
            )

            logger.info(
                f"[decision debug] score={signal['score']} "
                f"confidence={decision['confidence']} action={decision['action']}"
            )
            if signal["score"] < 65:
                logger.info(f"filtered signal: {signal['level'].upper()} {signal['score']}")
                continue

            if should_send_analysis_message():
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"{signal_prefix}\n{alpha_prefix}\n{decision_prefix}\n[autonomous: {keyword}]\n\n{answer}"
                )

        except asyncio.TimeoutError:
            logger.warning(f"[agent timeout] browser step timed out: {keyword}")
            await reset_shared_browser()
            await asyncio.sleep(300)
            continue

        except Exception as e:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"autonomous error: {str(e)}"
            )

        await asyncio.sleep(300)


async def agent_loop(chat_id, name):
    global last_trade_action

    logger.info(f"[agent loop started] {name}")

    profile = AGENT_PROFILES[name]
    keyword = profile["keyword"]

    while True:
        try:
            url = build_x_search_url(keyword)

            body = await asyncio.wait_for(
                read_agent_browser_body(name, url),
                timeout=45,
            )

            logger.info(f"[signal pipeline] raw body: {name} len={len(body)}")
            logger.info(f"[signal pipeline] quality check: {name}")
            if is_bad_x_page(body):
                logger.info("[x quality] bad page, skip analysis")
                await asyncio.sleep(300)
                continue

            raw_body = body
            logger.info(f"[signal pipeline] quality ok: {name}")
            logger.info(f"[signal pipeline] filtering: {name}")
            body = await asyncio.wait_for(
                asyncio.to_thread(filter_new_signals, f"agent:{name}", body),
                timeout=20,
            )
            logger.info(f"[signal pipeline] filtered: {name} len={len(body)}")

            if not body:
                if DEBUG_BYPASS_SIGNAL_FILTER:
                    logger.info(f"[signal pipeline] debug bypass dedupe: {name}")
                    body = raw_body[:12000]
                else:
                    logger.info(f"[signal pipeline] no new signals: {name}")
                    await asyncio.sleep(300)
                    continue

            if not body:
                logger.info(f"[signal pipeline] no new signals: {name}")
                await asyncio.sleep(300)
                continue

            if len(body) > 16000:
                body = body[:16000]

            prompt = f"""
you are {profile['role']}.

focus:
{profile['focus']}

analyze this X search page.

output format:
1. executive conclusion
2. top high-signal items
3. key accounts
4. bullish / positive signals
5. bearish / risk signals
6. scam / manipulation / abnormal activity
7. final score 0-100
8. what to monitor next

content:
{body}
"""

            logger.info(f"[llm] starting analysis: {name}")
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.chat.completions.create,
                        model=DEEPSEEK_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "you are a senior crypto intelligence analyst. be concise, factual, and high-signal."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=0.2
                    ),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                logger.warning(f"[llm timeout] analysis timed out: {name}")
                await asyncio.sleep(300)
                continue
            except Exception as e:
                logger.error(f"[llm error] {name}: {e}")
                await asyncio.sleep(300)
                continue

            answer = response.choices[0].message.content
            logger.info(f"[llm] analysis received: {name} len={len(answer)}")

            if len(answer) > 4000:
                answer = answer[:4000]

            signal = score_signal(answer, agent_name=name)
            signal_prefix = (
                f"[signal: {signal['level'].upper()} {signal['score']}] "
                f"{signal['reason']}"
            )
            whale = detect_whale_activity(answer)
            narrative = detect_narrative(answer)
            alpha = compute_alpha(signal, whale, narrative)
            alpha_prefix = (
                f"[alpha: {alpha['alpha_score']} | "
                f"whale: {'yes' if whale['whale'] else 'no'} | "
                f"narrative: {narrative['narrative']}]"
            )
            market_state = get_btc_market_state("BTCUSDT")
            market_price = market_state.get("price")
            if market_price is None:
                market_price = get_btc_price()
            logger.info(
                f"[market state] bias={market_state.get('market_bias')} "
                f"score={market_state.get('score')} "
                f"imbalance={market_state.get('orderbook_imbalance')} "
                f"volume_ratio={market_state.get('volume_ratio_1m')} "
                f"bb={market_state.get('bb_position')} "
                f"breakout={market_state.get('breakout')} "
                f"bull_count={market_state.get('bullish_count')} "
                f"bear_count={market_state.get('bearish_count')} "
                f"confirm_count={market_state.get('confirmation_count')} "
                f"bull_reasons={market_state.get('bullish_reasons')} "
                f"bear_reasons={market_state.get('bearish_reasons')} "
                f"reason={market_state.get('reason')}"
            )
            market_candidate = build_market_candidate(market_state)
            logger.info(
                f"[market candidate] action={market_candidate['action']} "
                f"confidence={market_candidate['confidence']} "
                f"reason={market_candidate['reason']}"
            )
            decision = generate_decision(
                signal,
                alpha,
                whale,
                narrative,
                answer,
                symbol=name,
                current_price=market_price,
            )
            price_snapshot = {
                "current_price": market_price,
                "previous_price": previous_market_prices.get(name),
            }
            direction_adjustment = adjust_decision_for_market_direction(
                decision,
                market_state,
                price_snapshot,
            )
            decision = direction_adjustment["decision"]
            logger.info(
                f"[decision direction] "
                f"original_action={direction_adjustment['original_action']} "
                f"final_action={direction_adjustment['final_action']} "
                f"changed={direction_adjustment['changed']} "
                f"reason={direction_adjustment['reason']} "
                f"market_bias={market_state.get('market_bias')} "
                f"market_score={market_state.get('score')} "
                f"confirmation_count={market_state.get('confirmation_count')} "
                f"current_price={price_snapshot.get('current_price')} "
                f"previous_price={price_snapshot.get('previous_price')}"
            )
            record_market_candidate(
                datetime.utcnow().isoformat(),
                "BTCUSDT",
                market_price,
                market_candidate,
                market_state,
                decision,
            )
            try:
                logger.info("[tg debug] sending analysis preview")
                debug_prefix = ""
                if decision["confidence"] < 70:
                    debug_prefix = "[DEBUG LOW SIGNAL]\n"

                if should_send_analysis_message():
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"{debug_prefix}{answer[:800]}"
                    )
            except Exception as e:
                logger.error(f"[tg debug error] {e}")

            price = extract_price_from_text(answer) or market_price
            record_decision(
                datetime.utcnow().isoformat(),
                {**decision, "narrative": narrative["narrative"]},
                price,
                name,
            )
            evaluate_decisions(market_price)
            if await process_trade_cycle(
                name,
                chat_id,
                decision,
                market_price,
                price_snapshot,
                market_state,
                market_candidate,
                direction_adjustment,
                signal,
                alpha,
                narrative,
            ):
                continue
            decision_prefix = (
                f"[decision: {decision['action'].upper()} | "
                f"confidence: {decision['confidence']} | "
                f"timeframe: {decision['timeframe']}]\n"
                f"reason: {decision['reason']}\n"
                f"risk: {decision['risk']}"
            )

            logger.info(
                f"[decision debug] score={signal['score']} "
                f"confidence={decision['confidence']} action={decision['action']}"
            )
            if signal["score"] < 65:
                logger.info(f"filtered signal: {signal['level'].upper()} {signal['score']}")
                continue

            if should_send_analysis_message():
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"{signal_prefix}\n{alpha_prefix}\n{decision_prefix}\n[agent:{name}]\n\n{answer}"
                )

        except asyncio.TimeoutError:
            logger.warning(f"[agent timeout] browser step timed out: {name}")
            try:
                await reset_agent_browser(name)
            except Exception as reset_error:
                logger.warning(f"agent browser reset error {name}: {reset_error}")
            await reset_shared_browser()
            await asyncio.sleep(300)
            continue

        except Exception as e:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"agent error {name}: {str(e)}\n\nself-healing: resetting browser context"
            )

            try:
                await reset_agent_browser(f"agent_{name}")
            except Exception as reset_error:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"self-healing reset error {name}: {str(reset_error)}"
                )

        await asyncio.sleep(300)


async def run_bot():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(TypeHandler(Update, access_control), group=-1)

    register_handlers(
        app,
        autonomous_tasks,
        autonomous_loop,
        agent_loop,
        save_autonomous_tasks,
        AGENT_PROFILES,
    )

    logger.info("hermes telegram bot started")

    try:
        await app.initialize()
        await app.start()
        await restore_autonomous_tasks(app)
        asyncio.create_task(daily_report_loop(app.bot))
        await app.updater.start_polling()
        await asyncio.Event().wait()
    except Conflict:
        logger.warning(
            "Another Telegram bot instance is already polling. Stop the other instance before running this one."
        )
    finally:
        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
        except Exception as e:
            logger.warning(f"updater stop error: {e}")

        try:
            if app.running:
                await app.stop()
        except Exception as e:
            logger.warning(f"application stop error: {e}")

        try:
            await app.shutdown()
        except Exception as e:
            logger.warning(f"application shutdown error: {e}")


def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("hermes telegram bot stopped")

if __name__ == "__main__":
    main()
