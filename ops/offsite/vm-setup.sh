#!/usr/bin/env bash
# 实验室虚拟机一键配置：内网资料库(Filebrowser) + 异地备份拉取
# 在 VM 上以 xiazhiyuan 身份执行：sudo bash vm-setup.sh <FILEBROWSER_ADMIN_PASSWORD>
set -euo pipefail

FB_PASS="${1:?用法: sudo bash vm-setup.sh <Filebrowser管理员密码>}"
RUN_USER="${SUDO_USER:-xiazhiyuan}"
RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)

echo "==> 1/6 Docker 镜像加速"
if [ ! -f /etc/docker/daemon.json ]; then
    cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.m.daocloud.io", "https://docker.xuanyuan.me"]
}
JSON
    systemctl restart docker
fi

echo "==> 2/6 目录结构"
install -d -m 775 /srv/esta-files
install -d -m 755 /srv/esta-files/{培训资料,竞赛资料,内部文档,软件工具,影音素材}
install -d -m 755 /opt/filebrowser
chown -R "$RUN_USER":"$RUN_USER" /srv/esta-files

echo "==> 3/6 Filebrowser 容器"
cat > /opt/filebrowser/docker-compose.yml <<YML
name: esta-files
services:
  filebrowser:
    image: filebrowser/filebrowser:v2
    restart: unless-stopped
    user: "$(id -u "$RUN_USER"):$(id -g "$RUN_USER")"
    ports:
      - "0.0.0.0:8080:80"
    volumes:
      - /srv/esta-files:/srv
      - /opt/filebrowser/database:/database
      - /opt/filebrowser/config:/config
    environment:
      FB_DATABASE: /database/filebrowser.db
    logging:
      driver: json-file
      options: { max-size: "5m", max-file: "2" }
YML
install -d -o "$RUN_USER" -g "$RUN_USER" /opt/filebrowser/database /opt/filebrowser/config
cd /opt/filebrowser
docker compose pull -q
docker compose up -d
sleep 6
# 初始化管理员密码与中文/品牌设置
docker compose exec -T filebrowser filebrowser config set --locale zh-cn --branding.name "HEU ESTA 内网资料库" --database /database/filebrowser.db >/dev/null 2>&1 || true
docker compose exec -T filebrowser filebrowser users update admin --password "$FB_PASS" --database /database/filebrowser.db >/dev/null 2>&1 \
  || docker compose exec -T filebrowser filebrowser users add admin "$FB_PASS" --perm.admin --database /database/filebrowser.db >/dev/null 2>&1 || true
docker compose restart >/dev/null

echo "==> 4/6 桥接网卡静态 IP（保持 192.168.1.112 不变）"
cat > /etc/netplan/60-esta-static.yaml <<'YAML'
network:
  version: 2
  ethernets:
    ens33:
      dhcp4: false
      addresses: [192.168.1.112/24]
YAML
chmod 600 /etc/netplan/60-esta-static.yaml
netplan apply || true

echo "==> 5/6 异地备份（每日 04:30 从云端拉取）"
if [ ! -f "$RUN_HOME/.ssh/id_ed25519" ]; then
    sudo -u "$RUN_USER" ssh-keygen -t ed25519 -f "$RUN_HOME/.ssh/id_ed25519" -N "" -q
fi
install -d -o "$RUN_USER" -g "$RUN_USER" "$RUN_HOME/bin"
cp /tmp/heuesta-pull-backup.sh "$RUN_HOME/bin/heuesta-pull-backup.sh"
sed -i 's/\r$//' "$RUN_HOME/bin/heuesta-pull-backup.sh"
chmod +x "$RUN_HOME/bin/heuesta-pull-backup.sh"
chown "$RUN_USER":"$RUN_USER" "$RUN_HOME/bin/heuesta-pull-backup.sh"
CRON_LINE="30 4 * * * $RUN_HOME/bin/heuesta-pull-backup.sh"
( sudo -u "$RUN_USER" crontab -l 2>/dev/null | grep -vF "heuesta-pull-backup" ; echo "$CRON_LINE" ) | sudo -u "$RUN_USER" crontab -

echo "==> 6/6 完成，输出关键信息"
echo "--- VM 备份公钥（需装入云端 backup-puller）---"
cat "$RUN_HOME/.ssh/id_ed25519.pub"
echo "--- Filebrowser ---"
docker ps --format '{{.Names}} {{.Status}}' | grep filebrowser || true
echo "内网地址: http://192.168.1.112:8080"
