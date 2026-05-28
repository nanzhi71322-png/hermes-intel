"""Fix duplicate env keys on remote /opt/hermes/.env."""
from __future__ import annotations

from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ENV_FILE = ROOT / ".env.deploy.local"

PREFERRED_KEYS = [
    "TRADING_MODE",
    "TRADING_TESTNET",
    "EXCHANGE_ID",
    "DEFAULT_SYMBOL",
    "MAX_POSITION_USD",
    "MAX_DAILY_LOSS_USD",
    "MAX_OPEN_POSITIONS",
    "BINANCE_API_KEY",
    "BINANCE_SECRET",
]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def dedupe_env(existing: str, preferred: dict[str, str]) -> str:
    result: list[str] = []
    seen: set[str] = set()

    for line in existing.splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in preferred:
                if key in seen:
                    continue
                result.append(f"{key}={preferred[key]}")
                seen.add(key)
                continue
        result.append(line)

    for key in PREFERRED_KEYS:
        if key in preferred and key not in seen:
            if result and result[-1].strip():
                result.append("")
            result.append(f"{key}={preferred[key]}")
            seen.add(key)

    text = "\n".join(result)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def main() -> None:
    deploy_env = load_env(DEPLOY_ENV_FILE)
    remote_env_path = deploy_env.get("DEPLOY_ENV_PATH", "/opt/hermes/.env")
    preferred = {key: deploy_env[key] for key in PREFERRED_KEYS if deploy_env.get(key)}

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        deploy_env["DEPLOY_SSH_HOST"],
        port=int(deploy_env.get("DEPLOY_SSH_PORT", "22")),
        username=deploy_env["DEPLOY_SSH_USER"],
        password=deploy_env["DEPLOY_SSH_PASSWORD"],
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = client.open_sftp()
    with sftp.open(remote_env_path, "r") as remote_file:
        existing = remote_file.read().decode("utf-8")
    merged = dedupe_env(existing, preferred)
    with sftp.open(remote_env_path, "w") as remote_file:
        remote_file.write(merged.encode("utf-8"))
    sftp.close()

    _, stdout, _ = client.exec_command(
        f"grep TRADING_MODE {remote_env_path}; systemctl restart hermes-bot; sleep 2; "
        f"cd /opt/hermes/tg-bot && source venv/bin/activate && "
        f"ENV_FILE=/opt/hermes/.env python -c \""
        f"from config.trading import TRADING_MODE, is_live_mode; "
        f"from trading.factory import get_executor; "
        f"print('loaded_mode='+TRADING_MODE); print('executor='+get_executor().mode); "
        f"print('is_live='+str(is_live_mode()))\"; systemctl is-active hermes-bot"
    )
    print(stdout.read().decode())
    client.close()


if __name__ == "__main__":
    main()
