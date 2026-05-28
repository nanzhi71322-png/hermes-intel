"""Run exchange connection test on remote server."""
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
        f"cd {remote_path} && source venv/bin/activate && "
        f"ENV_FILE=/opt/hermes/.env python scripts/test_exchange_connection.py"
    )
    _, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.close()
    print(out)
    if err.strip():
        print("STDERR:", err)


if __name__ == "__main__":
    main()
