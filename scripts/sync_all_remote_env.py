"""Check and sync tg-bot/.env on remote (systemd EnvironmentFiles)."""
from pathlib import Path
import paramiko

deploy = {}
for line in Path(r"c:\hermes\tg-bot\.env.deploy.local").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        deploy[k.strip()] = v.strip()

keys = [
    "TRADING_MODE", "TRADING_TESTNET", "EXCHANGE_ID", "DEFAULT_SYMBOL",
    "MAX_POSITION_USD", "MAX_DAILY_LOSS_USD", "MAX_OPEN_POSITIONS",
    "BINANCE_API_KEY", "BINANCE_SECRET",
    "DAILY_REPORT_ENABLED", "DAILY_REPORT_HOUR_UTC", "DAILY_REPORT_MINUTE_UTC",
    "OBSERVATION_DAYS", "SEND_REPORT_ON_START",
]
updates = {k: deploy[k] for k in keys if deploy.get(k)}
defaults = {
    "DAILY_REPORT_ENABLED": "true",
    "DAILY_REPORT_HOUR_UTC": "1",
    "DAILY_REPORT_MINUTE_UTC": "0",
    "OBSERVATION_DAYS": "3",
    "SEND_REPORT_ON_START": "true",
}
for key, value in defaults.items():
    updates.setdefault(key, value)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(deploy["DEPLOY_SSH_HOST"], port=22, username=deploy["DEPLOY_SSH_USER"],
          password=deploy["DEPLOY_SSH_PASSWORD"], timeout=15, allow_agent=False, look_for_keys=False)

for env_path in ("/opt/hermes/.env", "/opt/hermes/tg-bot/.env"):
    sftp = c.open_sftp()
    try:
        existing = sftp.open(env_path, "r").read().decode("utf-8")
    except OSError:
        existing = ""
    lines = existing.splitlines()
    seen = set()
    out = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                if key in seen:
                    continue
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key in updates:
        if key not in seen:
            out.append(f"{key}={updates[key]}")
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    with sftp.open(env_path, "w") as f:
        f.write(text.encode("utf-8"))
    sftp.close()
    print(f"updated {env_path}")

_, o, _ = c.exec_command(
    "grep -E '^(DAILY_REPORT|OBSERVATION|TRADING_MODE)=' /opt/hermes/.env; "
    "systemctl restart hermes-bot; sleep 5; "
    "grep 'daily report' /opt/hermes/logs/tg.log | tail -5; "
    "systemctl is-active hermes-bot"
)
print(o.read().decode())
c.close()
