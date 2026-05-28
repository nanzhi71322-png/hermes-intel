#!/usr/bin/env python3
"""暂停远程 hermes-bot 服务。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_LOCAL = ROOT / ".env.deploy.local"


def main() -> None:
    if not DEPLOY_LOCAL.exists():
        print("无 .env.deploy.local，跳过远程停止")
        return

    deploy: dict[str, str] = {}
    for line in DEPLOY_LOCAL.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            deploy[k.strip()] = v.strip()

    import paramiko

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        deploy["DEPLOY_SSH_HOST"],
        port=int(deploy.get("DEPLOY_SSH_PORT", "22")),
        username=deploy.get("DEPLOY_SSH_USER", "root"),
        password=deploy["DEPLOY_SSH_PASSWORD"],
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    _, stdout, _ = c.exec_command("systemctl stop hermes-bot; systemctl is-active hermes-bot || echo inactive")
    print(stdout.read().decode().strip())
    c.close()


if __name__ == "__main__":
    main()
