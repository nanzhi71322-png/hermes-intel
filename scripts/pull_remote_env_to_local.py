#!/usr/bin/env python3
"""从远程服务器拉取 /opt/hermes/.env 到本地快照（不提交 Git）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_LOCAL = ROOT / ".env.deploy.local"
OUT = ROOT / ".env.remote.snapshot"
EXAMPLE = ROOT / ".env.example"


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> None:
    if not DEPLOY_LOCAL.exists():
        print(f"缺少 {DEPLOY_LOCAL.name}，无法 SSH 拉取")
        sys.exit(1)

    deploy = _parse_env(DEPLOY_LOCAL.read_text(encoding="utf-8"))
    host = deploy.get("DEPLOY_SSH_HOST")
    user = deploy.get("DEPLOY_SSH_USER", "root")
    password = deploy.get("DEPLOY_SSH_PASSWORD")
    remote_path = deploy.get("DEPLOY_ENV_PATH", "/opt/hermes/.env")
    if not host or not password:
        print("DEPLOY_SSH_HOST / DEPLOY_SSH_PASSWORD 未配置")
        sys.exit(1)

    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=int(deploy.get("DEPLOY_SSH_PORT", "22")),
        username=user,
        password=password,
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = client.open_sftp()
    try:
        remote_text = sftp.open(remote_path, "r").read().decode("utf-8")
    except OSError as exc:
        print(f"读取远程失败 {remote_path}: {exc}")
        sys.exit(1)
    finally:
        sftp.close()
        client.close()

    remote = _parse_env(remote_text)
    key_order = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ALLOWED_CHAT_IDS",
        "DEEPSEEK_API_KEY",
        "TRADING_MODE",
        "TRADING_TESTNET",
        "EXCHANGE_ID",
        "DEFAULT_SYMBOL",
        "BINANCE_API_KEY",
        "BINANCE_SECRET",
        "MAX_POSITION_USD",
        "MAX_DAILY_LOSS_USD",
        "MAX_OPEN_POSITIONS",
    ]
    lines = [
        "# Pulled from remote — DO NOT COMMIT",
        f"# source: {remote_path}",
        "",
    ]
    for key in key_order:
        if key in remote:
            lines.append(f"{key}={remote[key]}")
    for key in sorted(remote.keys()):
        if key not in key_order:
            lines.append(f"{key}={remote[key]}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {OUT}")

    # 合并到本地 .env（仅补缺失键，不覆盖已有非空值）
    local_env = ROOT / ".env"
    local = _parse_env(local_env.read_text(encoding="utf-8")) if local_env.exists() else {}
    merged = dict(local)
    filled = 0
    for key, val in remote.items():
        if val and not merged.get(key):
            merged[key] = val
            filled += 1
    if filled:
        body = []
        if local_env.exists():
            for line in local_env.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k = line.split("=", 1)[0].strip()
                    if k in merged and k in remote and not local.get(k) and remote.get(k):
                        body.append(f"{k}={merged[k]}")
                        del merged[k]
                    else:
                        body.append(line)
                else:
                    body.append(line)
        else:
            body = list(EXAMPLE.read_text(encoding="utf-8").splitlines()) if EXAMPLE.exists() else []
        for k, v in sorted(merged.items()):
            if k not in {ln.split("=", 1)[0].strip() for ln in body if "=" in ln and not ln.startswith("#")}:
                body.append(f"{k}={v}")
        local_env.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"已向 .env 补全 {filled} 个缺失键")


if __name__ == "__main__":
    main()
