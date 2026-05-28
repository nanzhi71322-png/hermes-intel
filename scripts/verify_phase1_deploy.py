"""Verify Phase 1 deployment on remote server."""
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    deploy_env = load_env(ROOT / ".env.deploy.local")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        deploy_env["DEPLOY_SSH_HOST"],
        port=int(deploy_env.get("DEPLOY_SSH_PORT", "22")),
        username=deploy_env["DEPLOY_SSH_USER"],
        password=deploy_env["DEPLOY_SSH_PASSWORD"],
        timeout=15,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = (
        "grep TRADING_MODE /opt/hermes/.env || true; "
        "grep ALLOWED_CHAT_IDS /opt/hermes/.env || true; "
        "test -f /opt/hermes/tg-bot/pipeline/trade_pipeline.py && echo PIPELINE_OK || echo PIPELINE_MISSING; "
        "test -f /opt/hermes/tg-bot/trading/factory.py && echo TRADING_OK || echo TRADING_MISSING; "
        "systemctl is-active hermes-bot; "
        "tail -5 /opt/hermes/logs/tg.log"
    )
    _, stdout, _ = client.exec_command(cmd)
    print(stdout.read().decode())
    client.close()


if __name__ == "__main__":
    main()
