import asyncio
import json

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
from intel.market_price import get_btc_price
from intel.opportunity_engine import generate_decision, mark_trade_opened
from intel.paper_trading import execute_virtual_trade, update_positions
from intel.signal_engine import score_signal
from memory.signals import filter_new_signals
from utils.logging import setup_logging
from utils.urls import build_x_search_url

ensure_runtime_dirs()
setup_logging()

autonomous_tasks = {}

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


async def autonomous_loop(chat_id, keyword):
    while True:
        try:
            url = build_x_search_url(keyword)

            async with browser_manager.browser_lock:
                await browser_open(url)

                await browser_manager.browser_page.wait_for_timeout(3000)

                await browser_manager.browser_page.mouse.wheel(0, 1200)

                await browser_manager.browser_page.wait_for_timeout(2000)

                body = await browser_manager.browser_page.locator("body").inner_text(timeout=8000)

            if is_bad_x_page(body):
                logger.info("[x quality] bad page, skip analysis")
                await asyncio.sleep(300)
                continue

            body = filter_new_signals(keyword, body)

            if not body:
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

            response = await asyncio.to_thread(
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
            )

            answer = response.choices[0].message.content

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
            market_price = get_btc_price()
            decision = generate_decision(
                signal,
                alpha,
                whale,
                narrative,
                answer,
                symbol=keyword,
                current_price=market_price,
            )
            price = extract_price_from_text(answer)
            record_decision(
                datetime.utcnow().isoformat(),
                {**decision, "narrative": narrative["narrative"]},
                price,
                keyword,
            )
            evaluate_decisions()
            if market_price is not None and 30000 <= market_price <= 150000:
                if decision["confidence"] >= 80:
                    opened_position = execute_virtual_trade(
                        decision,
                        market_price,
                        keyword,
                        metadata={
                            "confidence": decision["confidence"],
                            "alpha_score": alpha["alpha_score"],
                            "signal_score": signal["score"],
                            "narrative": narrative["narrative"],
                            "action": decision["action"],
                        },
                    )
                    if opened_position:
                        logger.info(
                            f"[trade opened] action: {decision['action']} "
                            f"confidence: {decision['confidence']} "
                            f"alpha: {alpha['alpha_score']}"
                        )
                        mark_trade_opened(keyword)
                update_positions(market_price, keyword)
            else:
                logger.info("invalid price, skip trading")
            decision_prefix = (
                f"[decision: {decision['action'].upper()} | "
                f"confidence: {decision['confidence']} | "
                f"timeframe: {decision['timeframe']}]\n"
                f"reason: {decision['reason']}\n"
                f"risk: {decision['risk']}"
            )

            if signal["level"] not in ("high", "critical") and signal["score"] < 70:
                logger.info(f"filtered signal: {signal['level'].upper()} {signal['score']}")
                continue

            await app.bot.send_message(
                chat_id=chat_id,
                text=f"{signal_prefix}\n{alpha_prefix}\n{decision_prefix}\n[autonomous: {keyword}]\n\n{answer}"
            )

        except Exception as e:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"autonomous error: {str(e)}"
            )

        await asyncio.sleep(300)


async def agent_loop(chat_id, name):
    logger.info(f"[agent loop started] {name}")

    profile = AGENT_PROFILES[name]
    keyword = profile["keyword"]

    while True:
        try:
            url = build_x_search_url(keyword)

            async with browser_manager.browser_lock:
                await init_browser()

                await browser_manager.browser_page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await browser_manager.browser_page.wait_for_timeout(3000)

                for _ in range(3):
                    await browser_manager.browser_page.mouse.wheel(0, 1200)
                    await browser_manager.browser_page.wait_for_timeout(1500)

                body = await browser_manager.browser_page.locator("body").inner_text(timeout=10000)

            if is_bad_x_page(body):
                logger.info("[x quality] bad page, skip analysis")
                await asyncio.sleep(300)
                continue

            body = filter_new_signals(f"agent:{name}", body)

            if not body:
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

            response = await asyncio.to_thread(
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
            )

            answer = response.choices[0].message.content

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
            market_price = get_btc_price()
            decision = generate_decision(
                signal,
                alpha,
                whale,
                narrative,
                answer,
                symbol=name,
                current_price=market_price,
            )
            price = extract_price_from_text(answer)
            record_decision(
                datetime.utcnow().isoformat(),
                {**decision, "narrative": narrative["narrative"]},
                price,
                name,
            )
            evaluate_decisions()
            if market_price is not None and 30000 <= market_price <= 150000:
                if decision["confidence"] >= 80:
                    opened_position = execute_virtual_trade(
                        decision,
                        market_price,
                        name,
                        metadata={
                            "confidence": decision["confidence"],
                            "alpha_score": alpha["alpha_score"],
                            "signal_score": signal["score"],
                            "narrative": narrative["narrative"],
                            "action": decision["action"],
                        },
                    )
                    if opened_position:
                        logger.info(
                            f"[trade opened] action: {decision['action']} "
                            f"confidence: {decision['confidence']} "
                            f"alpha: {alpha['alpha_score']}"
                        )
                        mark_trade_opened(name)
                update_positions(market_price, name)
            else:
                logger.info("invalid price, skip trading")
            decision_prefix = (
                f"[decision: {decision['action'].upper()} | "
                f"confidence: {decision['confidence']} | "
                f"timeframe: {decision['timeframe']}]\n"
                f"reason: {decision['reason']}\n"
                f"risk: {decision['risk']}"
            )

            if signal["level"] not in ("high", "critical") and signal["score"] < 70:
                logger.info(f"filtered signal: {signal['level'].upper()} {signal['score']}")
                continue

            await app.bot.send_message(
                chat_id=chat_id,
                text=f"{signal_prefix}\n{alpha_prefix}\n{decision_prefix}\n[agent:{name}]\n\n{answer}"
            )

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


async def on_startup(application):
    await restore_autonomous_tasks(application)


def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
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
        app.run_polling()
    except Conflict:
        logger.warning(
            "Another Telegram bot instance is already polling. Stop the other instance before running this one."
        )

if __name__ == "__main__":
    main()
