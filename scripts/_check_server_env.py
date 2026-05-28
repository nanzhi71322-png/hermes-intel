"""One-off helper: verify remote /opt/hermes/.env keys (values masked)."""
from pathlib import Path

import paramiko


def load_deploy_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    deploy_env = load_deploy_env(Path(__file__).resolve().parents[1] / ".env.deploy.local")
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
    _, stdout, _ = client.exec_command(
        "grep -E '^(TELEGRAM_BOT_TOKEN|DEEPSEEK_API_KEY|ALLOWED_CHAT_IDS)=' /opt/hermes/.env "
        "|| true"
    )
    lines = stdout.read().decode().strip().splitlines()
    client.close()

    for key in ("TELEGRAM_BOT_TOKEN", "DEEPSEEK_API_KEY", "ALLOWED_CHAT_IDS"):
        matched = next((line for line in lines if line.startswith(key + "=")), None)
        if not matched:
            print(f"{key}=MISSING")
            continue
        value = matched.split("=", 1)[1].strip()
        print(f"{key}=SET" if value else f"{key}=MISSING")


if __name__ == "__main__":
    main()
