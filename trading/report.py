"""交易绩效报告 — /tradereport（中文）。"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

from config.settings import BOT_HOME
from config.trading import TRADING_MODE, TRADING_PAUSED, TRADING_TESTNET, is_live_mode
from intel.feedback_engine import compute_statistics
from intel.paper_trading import PORTFOLIO_FILE
from trading.storage.live_portfolio import closed_stats, load_positions, recent_closed, recent_orders

BJT = timezone(timedelta(hours=8))

REASON_ZH = {
    "take_profit": "止盈",
    "stop_loss": "止损",
    "ttl": "超时平仓",
    "filled": "已成交",
    "closed": "已平仓",
    "failed": "失败",
    "close_failed": "平仓失败",
    "buy": "买入",
    "sell": "卖出",
}

NARRATIVE_ZH = {
    "etf": "ETF",
    "regulation": "监管",
    "macro": "宏观",
    "meme": "Meme",
    "scam": "诈骗",
    "breaking": "突发",
    "news": "新闻",
    "unknown": "未知",
}


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _zh_reason(value: str | None) -> str:
    if not value:
        return "未知"
    return REASON_ZH.get(str(value), str(value))


def _zh_narrative(value: str | None) -> str:
    if not value:
        return "未知"
    key = str(value).lower()
    return NARRATIVE_ZH.get(key, str(value))


def _mode_label() -> str:
    if is_live_mode():
        return "实盘" if not TRADING_TESTNET else "Testnet 模拟实盘"
    return "纸面模拟"


def _candidate_stats_summary() -> str:
    path = os.path.join(BOT_HOME, "data", "candidate_stats.json")
    stats = _read_json(path)
    if not stats:
        return "市场候选统计：暂无数据"

    lines = ["市场候选边缘："]
    action_zh = {"long": "做多", "short": "做空"}
    for horizon in ("60s", "180s", "300s"):
        horizon_stats = stats.get(horizon, {})
        for action, action_stats in horizon_stats.items():
            count = action_stats.get("count", 0)
            if count < 5:
                continue
            win_rate = action_stats.get("win_rate", 0.0)
            avg_pnl = action_stats.get("avg_pnl_pct", 0.0)
            lines.append(
                f"  {horizon} {action_zh.get(action, action)}："
                f"样本={count} 胜率={win_rate:.2%} 均收益={avg_pnl:.4%}"
            )
    return "\n".join(lines) if len(lines) > 1 else "市场候选统计：数据积累中"


def build_tradereport_text() -> str:
    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M 北京时间")
    paused = "是" if TRADING_PAUSED else "否"

    lines = [
        "📊 Hermes 交易日报",
        f"时间：{now_bjt}",
        f"模式：{_mode_label()}",
        f"交易暂停：{paused}",
    ]

    feedback = compute_statistics()
    lines.extend(
        [
            "",
            "【决策反馈】",
            f"  已评估：{feedback.get('total_trades', 0)} 笔",
            f"  做多胜率：{feedback.get('long_win_rate', 0)}%",
            f"  做空胜率：{feedback.get('short_win_rate', 0)}%",
            f"  最佳叙事：{_zh_narrative(feedback.get('best_narrative'))}",
            f"  最差叙事：{_zh_narrative(feedback.get('worst_narrative'))}",
        ]
    )

    if is_live_mode():
        live_closed = closed_stats()
        open_count = len(load_positions())
        lines.extend(
            [
                "",
                "【Live 交易】",
                f"  持仓中：{open_count} 笔",
                f"  近期平仓：{live_closed.get('count', 0)} 笔",
                f"  胜率：{live_closed.get('win_rate', 0):.1%}",
                f"  累计盈亏：${live_closed.get('total_pnl', 0):.4f}",
            ]
        )
        recent = recent_closed(3)
        if recent:
            lines.append("  最近平仓：")
            for item in recent:
                lines.append(
                    f"    {_zh_reason(item.get('reason'))} "
                    f"盈亏=${float(item.get('pnl', 0)):.4f} "
                    f"({float(item.get('pnl_pct', 0)):.2%})"
                )
        orders = recent_orders(3)
        if orders:
            lines.append("  最近订单：")
            for order in orders:
                lines.append(
                    f"    {_zh_reason(order.get('status'))} "
                    f"{_zh_reason(order.get('side'))} {order.get('symbol')}"
                )
    else:
        paper = _read_json(PORTFOLIO_FILE)
        lines.extend(
            [
                "",
                "【纸面模拟】",
                f"  余额：${float(paper.get('balance', 0)):.2f}",
                f"  持仓：{len(paper.get('positions', []))} 笔",
            ]
        )

    lines.extend(["", _candidate_stats_summary()])
    return "\n".join(lines)


async def build_tradereport_text_async() -> str:
    return await asyncio.to_thread(build_tradereport_text)
