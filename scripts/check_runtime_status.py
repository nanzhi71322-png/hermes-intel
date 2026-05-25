#!/usr/bin/env python3
"""检查 Hermes 运行状态 — 本地数据、回测结果、远程 bot 服务。"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "backtest"
RESULTS_DIR = DATA_DIR / "results"
PORTFOLIO_FILE = ROOT / "data" / "paper_portfolio.json"
FEEDBACK_FILE = Path(os.getenv("BOT_HOME", str(ROOT))) / "decision_feedback.jsonl"


def _file_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 3600


def check_local_data() -> list[str]:
    lines = ["[本地数据缓存]"]
    for csv in sorted(DATA_DIR.glob("*.csv")):
        age = _file_age_hours(csv)
        lines.append(f"  {csv.name}: {sum(1 for _ in open(csv, encoding='utf-8')) - 1} rows, {age:.1f}h ago")
    if not list(DATA_DIR.glob("*.csv")):
        lines.append("  (无缓存，需运行 run_strategy_compare.py --refresh)")
    return lines


def check_latest_results() -> list[str]:
    lines = ["[最新回测结果]"]
    if not RESULTS_DIR.exists():
        lines.append("  (无结果)")
        return lines
    files = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:3]:
        age = _file_age_hours(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            summary = _summarize_result(path.name, payload)
        except (OSError, json.JSONDecodeError):
            summary = "parse error"
        lines.append(f"  {path.name} ({age:.1f}h ago): {summary}")
    if not files:
        lines.append("  (无结果)")
    return lines


def _summarize_result(name: str, payload: dict) -> str:
    if "ranking" in payload:
        ranking = payload["ranking"]
        if ranking:
            top = ranking[0]
            m = top.get("metrics", {})
            return f"best={top.get('label')} ret={m.get('total_return_pct', 0):.2f}% trades={m.get('total_trades', 0)}"
    if "compare" in payload:
        best = max(payload["compare"], key=lambda x: x.get("return_pct", -999))
        return f"best_tf={best.get('timeframe')} ret={best.get('return_pct', 0):.2f}%"
    m = payload.get("metrics", {})
    if m:
        return f"ret={m.get('total_return_pct', 0):.2f}% trades={m.get('total_trades', 0)}"
    return "unknown"


def check_paper_portfolio() -> list[str]:
    lines = ["[模拟盘持仓]"]
    if not PORTFOLIO_FILE.exists():
        lines.append(f"  文件不存在: {PORTFOLIO_FILE}")
        return lines
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        lines.append(f"  balance={data.get('balance')} open={len(data.get('positions', []))}")
    except (OSError, json.JSONDecodeError):
        lines.append("  读取失败")
    return lines


def check_feedback() -> list[str]:
    lines = ["[决策反馈]"]
    if not FEEDBACK_FILE.exists():
        lines.append(f"  文件不存在: {FEEDBACK_FILE}")
        return lines
    total = evaluated = wins = 0
    with open(FEEDBACK_FILE, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if row.get("result"):
                evaluated += 1
                if row.get("correct"):
                    wins += 1
    wr = (wins / evaluated * 100) if evaluated else 0
    lines.append(f"  total={total} evaluated={evaluated} win_rate={wr:.1f}%")
    return lines


def check_remote_bot() -> list[str]:
    lines = ["[远程 hermes-bot]"]
    deploy_file = ROOT / ".env.deploy.local"
    if not deploy_file.exists():
        lines.append("  .env.deploy.local 不存在，跳过远程检查")
        return lines
    try:
        import paramiko
    except ImportError:
        lines.append("  paramiko 未安装，跳过远程检查")
        return lines

    env: dict[str, str] = {}
    for line in deploy_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs = {
            "hostname": env["DEPLOY_SSH_HOST"],
            "port": int(env.get("DEPLOY_SSH_PORT", "22")),
            "username": env["DEPLOY_SSH_USER"],
            "timeout": 15,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if env.get("DEPLOY_SSH_PASSWORD"):
            connect_kwargs["password"] = env["DEPLOY_SSH_PASSWORD"]
        elif env.get("DEPLOY_SSH_KEY_PATH"):
            connect_kwargs["key_filename"] = env["DEPLOY_SSH_KEY_PATH"]
        else:
            lines.append("  无 SSH 凭证")
            return lines

        client.connect(**connect_kwargs)
        cmd = (
            "systemctl is-active hermes-bot; "
            "grep -E '^(TRADING_MODE|TRADING_TESTNET|TRADING_PAUSED)=' /opt/hermes/.env; "
            "tail -1 /opt/hermes/logs/tg.log 2>/dev/null || echo 'no log'"
        )
        _, stdout, _ = client.exec_command(cmd)
        output = stdout.read().decode("utf-8", errors="replace").strip().splitlines()
        for row in output[:6]:
            lines.append(f"  {row}")
    except Exception as exc:
        lines.append(f"  SSH 失败: {exc}")
    finally:
        client.close()
    return lines


def main() -> None:
    sections = [
        check_local_data(),
        check_latest_results(),
        check_paper_portfolio(),
        check_feedback(),
        check_remote_bot(),
    ]
    for section in sections:
        print("\n".join(section))
        print()


if __name__ == "__main__":
    main()
