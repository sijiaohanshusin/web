# -*- coding: utf-8 -*-
"""用密码首次连接实验室虚拟机：安装本机 SSH 公钥 + 采集系统信息。
用法: python vm_bootstrap.py <host> <user> <password>
"""
import sys
from pathlib import Path

import paramiko

host, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
pubkey = (Path.home() / ".ssh" / "id_ed25519.pub").read_text().strip()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=user, password=password, timeout=15)

CMDS = [
    ("install-key", (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"grep -qF '{pubkey}' ~/.ssh/authorized_keys 2>/dev/null || echo '{pubkey}' >> ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys && echo key-ok"
    )),
    ("os", "cat /etc/os-release | head -2"),
    ("kernel", "uname -r"),
    ("ip", "ip -4 addr show | grep -E 'inet ' | grep -v 127.0.0.1"),
    ("route", "ip route | head -3"),
    ("dns", "resolvectl status 2>/dev/null | grep -m1 'DNS Servers' || cat /etc/resolv.conf | grep nameserver | head -2"),
    ("internet", "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 6 https://www.baidu.com || echo FAIL"),
    ("cloud-ssh", "timeout 6 bash -c 'cat < /dev/null > /dev/tcp/123.57.6.128/22' 2>/dev/null && echo cloud-reachable || echo cloud-unreachable"),
    ("disk", "df -h / /home 2>/dev/null; lsblk -d -o NAME,SIZE,TYPE | grep disk"),
    ("mem", "free -h | head -2"),
    ("docker", "command -v docker >/dev/null && docker --version || echo no-docker"),
    ("sudo", f"echo '{password}' | sudo -S -p '' whoami 2>/dev/null || echo no-sudo"),
]

for name, cmd in CMDS:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    print(f"=== {name} ===")
    print(out if out else (err[:300] if err else "(empty)"))

client.close()
print("=== done ===")
