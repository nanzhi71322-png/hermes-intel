"""Verify TRADING_MODE and executor on remote server."""
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
    remote_path = deploy_env.get("DEPLOY_REMOTE_PATH", "/opt/hermes/tg-bot")
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
    cmd = (
        f"grep TRADING_MODE /opt/hermes/.env; "
        f"cd {remote_path} && source venv/bin/activate && "
        f"ENV_FILE=/opt/hermes/.env python -c \""
        f"from config.trading import TRADING_MODE, TRADING_TESTNET, is_live_mode; "
        f"from trading.factory import get_executor; "
        f"e=get_executor(); "
        f"print('TRADING_MODE='+TRADING_MODE); "
        f"print('TRADING_TESTNET='+str(TRADING_TESTNET)); "
        f"print('EXECUTOR='+e.mode); "
        f"print('IS_LIVE='+str(is_live_mode()))\""
    )
    _, stdout, stderr = client.exec_command(
        f"systemctl restart hermes-bot; sleep 2; {cmd}; systemctl is-active hermes-bot"
    )
    print(stdout.read().decode())
    err = stderr.read().decode().strip()
    if err:
        print("STDERR:", err)
    client.close()


if __name__ == "__main__":
    main()
