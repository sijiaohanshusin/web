#!/usr/bin/env bash
# 补齐 vm-setup 未完成的部分：Filebrowser 密码/中文、静态 IP（NM 方式）、cron、docker 组
set -uo pipefail

FB_PASS="${1:?用法: sudo bash vm-fix.sh <Filebrowser管理员密码>}"
RUN_USER="${SUDO_USER:-xiazhiyuan}"
RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)

echo "==> Filebrowser：停容器后用 CLI 设置（BoltDB 需独占）"
cd /opt/filebrowser
docker compose stop filebrowser >/dev/null
docker run --rm -v /opt/filebrowser/database:/database filebrowser/filebrowser:v2 \
    config set --locale zh-cn --branding.name "HEU ESTA 内网资料库" --database /database/filebrowser.db
docker run --rm -v /opt/filebrowser/database:/database filebrowser/filebrowser:v2 \
    users update admin --password "$FB_PASS" --database /database/filebrowser.db \
 || docker run --rm -v /opt/filebrowser/database:/database filebrowser/filebrowser:v2 \
    users add admin "$FB_PASS" --perm.admin --database /database/filebrowser.db
chown -R "$RUN_USER":"$RUN_USER" /opt/filebrowser/database
docker compose start filebrowser >/dev/null
echo "filebrowser configured"

echo "==> 静态 IP：通过 NetworkManager 固定 ens33 = 192.168.1.112"
nmcli con mod netplan-ens33 ipv4.method manual ipv4.addresses 192.168.1.112/24 ipv4.never-default yes 2>/dev/null \
  || nmcli con mod "有线连接 1" ipv4.method manual ipv4.addresses 192.168.1.112/24 ipv4.never-default yes 2>/dev/null || true
nmcli con up netplan-ens33 2>/dev/null || true
ip -4 addr show ens33 | grep inet

echo "==> cron：安装每日备份任务"
( sudo -u "$RUN_USER" crontab -l 2>/dev/null | grep -vF "heuesta-pull-backup" || true ; echo "30 4 * * * $RUN_HOME/bin/heuesta-pull-backup.sh" ) | sudo -u "$RUN_USER" crontab -
sudo -u "$RUN_USER" crontab -l | grep heuesta

echo "==> docker 组"
usermod -aG docker "$RUN_USER" || true

echo "==> 开机自启检查"
systemctl is-enabled docker >/dev/null || systemctl enable docker

echo "==> 全部完成"
