"""Run $5 testnet live order on remote server."""
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
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = (
        "cd /opt/hermes/tg-bot && source venv/bin/activate && "
        "ENV_FILE=/opt/hermes/.env python -c \""
        "from config.trading import TRADING_MODE, is_live_mode; "
        "from trading.execution.live import LiveExecutor; "
        "from trading.exchange.connector import ExchangeConnector; "
        "from config.trading import DEFAULT_SYMBOL; "
        "print('mode', TRADING_MODE, 'live', is_live_mode()); "
        "c=ExchangeConnector(); "
        "t=c.fetch_ticker(DEFAULT_SYMBOL); p=t['last']; "
        "e=LiveExecutor(connector=c); "
        "pos=e.open_position({'action':'long','confidence':99}, float(p), 'btc', 15.0, {'source':'remote_test'}); "
        "print('order', pos); "
        "c.close()\""
    )
    _, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode())
    err = stderr.read().decode().strip()
    if err:
        print("STDERR:", err)
    client.close()


if __name__ == "__main__":
    main()
