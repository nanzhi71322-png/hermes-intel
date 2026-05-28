"""Deploy tg-bot Phase 1 to remote server via SFTP."""
from __future__ import annotations

import os
import tarfile
import tempfile
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ENV_FILE = ROOT / ".env.deploy.local"

SKIP_DIRS = {"venv", "__pycache__", ".git", "data/backtest/results"}
SKIP_FILES = {".env", ".env.deploy.local"}


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    if rel.name in SKIP_FILES:
        return True
    if rel.suffix == ".pyc":
        return True
    return False


def build_tarball() -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    tmp.close()
    tar_path = Path(tmp.name)
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if should_skip(rel):
                continue
            tar.add(path, arcname=str(Path("tg-bot") / rel))
    return tar_path


def merge_remote_env(sftp: paramiko.SFTPClient, remote_env_path: str, local_env: dict[str, str]) -> None:
    try:
        with sftp.open(remote_env_path, "r") as remote_file:
            existing = remote_file.read().decode("utf-8")
    except OSError:
        existing = ""

    lines = existing.splitlines()
    keys_present = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            keys_present.add(line.split("=", 1)[0].strip())

    append_lines: list[str] = []
    trading_keys = {
        "TRADING_MODE": local_env.get("TRADING_MODE", "paper"),
        "TRADING_TESTNET": local_env.get("TRADING_TESTNET", "true"),
        "EXCHANGE_ID": local_env.get("EXCHANGE_ID", "binance"),
        "DEFAULT_SYMBOL": local_env.get("DEFAULT_SYMBOL", "BTC/USDT"),
        "MAX_POSITION_USD": local_env.get("MAX_POSITION_USD", "50"),
        "MAX_DAILY_LOSS_USD": local_env.get("MAX_DAILY_LOSS_USD", "20"),
        "MAX_OPEN_POSITIONS": local_env.get("MAX_OPEN_POSITIONS", "3"),
    }

    if local_env.get("BINANCE_API_KEY"):
        trading_keys["BINANCE_API_KEY"] = local_env["BINANCE_API_KEY"]
    if local_env.get("BINANCE_SECRET"):
        trading_keys["BINANCE_SECRET"] = local_env["BINANCE_SECRET"]

    for key, value in trading_keys.items():
        if key not in keys_present and value:
            append_lines.append(f"{key}={value}")

    if "ALLOWED_CHAT_IDS" not in keys_present:
        legacy_chat = next(
            (
                line.split("=", 1)[1].strip()
                for line in lines
                if line.startswith("TELEGRAM_CHAT_ID=")
            ),
            "",
        )
        if legacy_chat:
            append_lines.append(f"ALLOWED_CHAT_IDS={legacy_chat}")

    if not append_lines:
        return

    updated = existing
    if updated and not updated.endswith("\n"):
        updated += "\n"
    updated += "\n# Phase 1 trading vars\n"
    updated += "\n".join(append_lines) + "\n"

    with sftp.open(remote_env_path, "w") as remote_file:
        remote_file.write(updated.encode("utf-8"))


def main() -> None:
    if not DEPLOY_ENV_FILE.exists():
        raise SystemExit(f"missing {DEPLOY_ENV_FILE}")

    deploy_env = load_env(DEPLOY_ENV_FILE)
    host = deploy_env["DEPLOY_SSH_HOST"]
    user = deploy_env["DEPLOY_SSH_USER"]
    password = deploy_env["DEPLOY_SSH_PASSWORD"]
    port = int(deploy_env.get("DEPLOY_SSH_PORT", "22"))
    remote_path = deploy_env.get("DEPLOY_REMOTE_PATH", "/opt/hermes/tg-bot")
    remote_env_path = deploy_env.get("DEPLOY_ENV_PATH", "/opt/hermes/.env")

    tar_path = build_tarball()
    remote_tar = "/tmp/hermes-phase1.tar.gz"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=port,
        username=user,
        password=password,
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = client.open_sftp()
    sftp.put(str(tar_path), remote_tar)
    merge_remote_env(sftp, remote_env_path, deploy_env)
    sftp.close()

    commands = f"""
set -e
mkdir -p {remote_path}
tar -xzf {remote_tar} -C /opt/hermes --strip-components=0
cd {remote_path}
if [ ! -d venv ]; then python3.12 -m venv venv; fi
source venv/bin/activate
pip install -r requirements.txt -q
python -m py_compile tg_bot.py pipeline/trade_pipeline.py trading/factory.py
systemctl restart hermes-bot
sleep 2
systemctl is-active hermes-bot
tail -20 /opt/hermes/logs/tg.log || true
"""
    _, stdout, stderr = client.exec_command(commands)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.close()
    os.unlink(tar_path)

    print(out)
    if err.strip():
        print(err)


if __name__ == "__main__":
    main()
