"""Sync Binance + trading env vars to remote /opt/hermes/.env."""
from __future__ import annotations

from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ENV_FILE = ROOT / ".env.deploy.local"

SYNC_KEYS = [
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


def upsert_env_lines(existing: str, updates: dict[str, str]) -> str:
    lines = existing.splitlines()
    seen = set()
    new_lines: list[str] = []

    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                if key in seen:
                    continue
                new_lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        new_lines.append(line)

    missing = [key for key in SYNC_KEYS if key in updates and key not in seen]
    if missing:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# Binance / trading (synced)")
        for key in missing:
            new_lines.append(f"{key}={updates[key]}")

    text = "\n".join(new_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def main() -> None:
    if not DEPLOY_ENV_FILE.exists():
        raise SystemExit(f"missing {DEPLOY_ENV_FILE}")

    deploy_env = load_env(DEPLOY_ENV_FILE)
    updates = {key: deploy_env[key] for key in SYNC_KEYS if deploy_env.get(key)}

    if not updates.get("BINANCE_API_KEY") or not updates.get("BINANCE_SECRET"):
        raise SystemExit("BINANCE_API_KEY and BINANCE_SECRET must be set in .env.deploy.local")

    remote_env_path = deploy_env.get("DEPLOY_ENV_PATH", "/opt/hermes/.env")
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
    try:
        with sftp.open(remote_env_path, "r") as remote_file:
            existing = remote_file.read().decode("utf-8")
    except OSError:
        existing = ""

    merged = upsert_env_lines(existing, updates)
    with sftp.open(remote_env_path, "w") as remote_file:
        remote_file.write(merged.encode("utf-8"))
    sftp.close()
    client.close()

    print(f"synced {len(updates)} keys to {remote_env_path}")
    print("BINANCE_API_KEY=SET")
    print("BINANCE_SECRET=SET")


if __name__ == "__main__":
    main()
