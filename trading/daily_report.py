"""每日报表调度 — 3 天观察期自动推送 Telegram。"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone

from loguru import logger

from config.settings import ALLOWED_CHAT_IDS, BOT_HOME
from trading.report import build_tradereport_text_async

STATE_FILE = os.path.join(BOT_HOME, "data", "daily_report_state.json")

OBSERVATION_DAYS = int(os.getenv("OBSERVATION_DAYS", "3"))
DAILY_REPORT_ENABLED = os.getenv("DAILY_REPORT_ENABLED", "true").lower() == "true"
DAILY_REPORT_HOUR_UTC = int(os.getenv("DAILY_REPORT_HOUR_UTC", "1"))
DAILY_REPORT_MINUTE_UTC = int(os.getenv("DAILY_REPORT_MINUTE_UTC", "0"))
SEND_REPORT_ON_START = os.getenv("SEND_REPORT_ON_START", "true").lower() == "true"


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=True, indent=2)


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _observation_day(state: dict) -> int:
    start_raw = state.get("observation_start")
    if not start_raw:
        return 1
    start = date.fromisoformat(start_raw)
    delta = datetime.now(timezone.utc).date() - start
    return max(1, delta.days + 1)


def _observation_active(state: dict) -> bool:
    day = _observation_day(state)
    return day <= OBSERVATION_DAYS


def _build_header(state: dict) -> str:
    day = _observation_day(state)
    start = state.get("observation_start", "n/a")
    end = state.get("observation_end", "n/a")
    if _observation_active(state):
        return (
            f"🔭 观察期 第 {day}/{OBSERVATION_DAYS} 天\n"
            f"周期：{start} → {end}\n\n"
        )
    return "✅ 观察期已结束\n\n"


async def _send_report(bot, state: dict) -> None:
    body = await build_tradereport_text_async()
    text = _build_header(state) + body
    chat_ids = ALLOWED_CHAT_IDS or set()
    if not chat_ids:
        logger.warning("[daily report] no ALLOWED_CHAT_IDS configured")
        return

    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=text[:4000])
            logger.info(f"[daily report] sent to chat_id={chat_id}")
        except Exception as exc:
            logger.error(f"[daily report] send failed chat_id={chat_id}: {exc}")


def _init_observation(state: dict) -> dict:
    today = _today_utc()
    if not state.get("observation_start"):
        start = datetime.now(timezone.utc).date()
        end = start + timedelta(days=OBSERVATION_DAYS - 1)
        state["observation_start"] = start.isoformat()
        state["observation_end"] = end.isoformat()
        state["reports_sent"] = 0
        logger.info(
            f"[daily report] observation started {state['observation_start']} "
            f"-> {state['observation_end']}"
        )
    if state.get("last_report_date") != today:
        state.setdefault("reports_sent", 0)
    return state


async def send_daily_report_now(bot) -> None:
    state = _init_observation(_load_state())
    if not DAILY_REPORT_ENABLED:
        return
    if not _observation_active(state) and state.get("reports_sent", 0) >= OBSERVATION_DAYS:
        logger.info("[daily report] observation period finished, skip manual send")
        return
    await _send_report(bot, state)
    state["last_report_date"] = _today_utc()
    state["reports_sent"] = int(state.get("reports_sent", 0)) + 1
    _save_state(state)


async def daily_report_loop(bot) -> None:
    if not DAILY_REPORT_ENABLED:
        logger.info("[daily report] disabled")
        return

    state = _init_observation(_load_state())
    _save_state(state)

    if SEND_REPORT_ON_START and state.get("last_report_date") != _today_utc():
        if _observation_active(state):
            await _send_report(bot, state)
            state["last_report_date"] = _today_utc()
            state["reports_sent"] = int(state.get("reports_sent", 0)) + 1
            _save_state(state)

    logger.info(
        f"[daily report] scheduler started hour={DAILY_REPORT_HOUR_UTC:02d}:"
        f"{DAILY_REPORT_MINUTE_UTC:02d} UTC observation_days={OBSERVATION_DAYS}"
    )

    while True:
        try:
            now = datetime.now(timezone.utc)
            target = now.replace(
                hour=DAILY_REPORT_HOUR_UTC,
                minute=DAILY_REPORT_MINUTE_UTC,
                second=0,
                microsecond=0,
            )
            if target <= now:
                target += timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            logger.info(f"[daily report] next send at {target.isoformat()} ({sleep_seconds:.0f}s)")
            await asyncio.sleep(sleep_seconds)

            state = _init_observation(_load_state())
            if not _observation_active(state):
                logger.info("[daily report] observation period ended, scheduler stopping")
                if state.get("reports_sent", 0) < OBSERVATION_DAYS:
                    await _send_report(bot, state)
                    state["last_report_date"] = _today_utc()
                    state["reports_sent"] = int(state.get("reports_sent", 0)) + 1
                    _save_state(state)
                break

            if state.get("last_report_date") == _today_utc():
                continue

            await _send_report(bot, state)
            state["last_report_date"] = _today_utc()
            state["reports_sent"] = int(state.get("reports_sent", 0)) + 1
            _save_state(state)

            if int(state.get("reports_sent", 0)) >= OBSERVATION_DAYS:
                logger.info("[daily report] all observation reports sent")
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[daily report] scheduler error: {exc}")
            await asyncio.sleep(300)
