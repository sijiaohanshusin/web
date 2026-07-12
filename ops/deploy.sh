#!/usr/bin/env bash
# HEU ESTA 官网部署脚本（在服务器上执行）
# 用法：sudo /opt/heuesta/web/ops/deploy.sh
# 幂等：可重复执行；每次执行 = 拉最新代码 + 重建容器 + 同步学习中心 + 重载 nginx
#
# 注：服务器直连 github git 协议不通，但 codeload tarball 通道可用，
#     故通过下载 main 分支归档来更新代码（与旧版 heuesta-sync 相同的通道）。
set -euo pipefail

REPO_DIR=/opt/heuesta/web
ENV_FILE=/opt/heuesta/.env
ARCHIVE_URL="https://codeload.github.com/sijiaohanshusin/web/tar.gz/refs/heads/main"
COMPOSE="docker compose -f $REPO_DIR/ops/docker-compose.yml --env-file $ENV_FILE"

if [ ! -f "$ENV_FILE" ]; then
    echo "缺少 $ENV_FILE，请先从 ops/env.example 复制并填写" >&2
    exit 1
fi

echo "==> 下载最新代码（GitHub main 分支归档）"
tmp_archive=$(mktemp /tmp/heuesta-web.XXXXXX.tar.gz)
tmp_dir=$(mktemp -d /tmp/heuesta-web-src.XXXXXX)
cleanup() { rm -f "$tmp_archive"; rm -rf "$tmp_dir"; }
trap cleanup EXIT

curl --fail --location --retry 5 --retry-delay 5 --connect-timeout 15 \
    --output "$tmp_archive" "$ARCHIVE_URL"
tar -xzf "$tmp_archive" -C "$tmp_dir"
extracted_dir=$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)

install -d -m 755 "$REPO_DIR"
rsync -a --delete "$extracted_dir/" "$REPO_DIR/"
chmod +x "$REPO_DIR"/ops/*.sh

echo "==> 准备目录"
install -d -m 755 /srv/heuesta/static /srv/heuesta/media /srv/heuesta/pgdata /srv/heuesta/backups /srv/heuesta/site
# 容器内 appuser uid=1000 需要写入 static/media
chown -R 1000:1000 /srv/heuesta/static /srv/heuesta/media

echo "==> 同步学习中心静态文件"
rsync -a --delete "$REPO_DIR/learn/" /srv/heuesta/site/learn/
find /srv/heuesta/site -type d -exec chmod 755 {} +
find /srv/heuesta/site -type f -exec chmod 644 {} +

echo "==> 构建并启动容器"
$COMPOSE build
$COMPOSE up -d

echo "==> 等待应用就绪"
for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -H "Host: heuesta.cn" http://127.0.0.1:8001/; then
        echo "应用已就绪"
        break
    fi
    if [ "$i" = 60 ]; then
        echo "应用启动超时，查看日志：$COMPOSE logs app" >&2
        exit 1
    fi
    sleep 2
done

echo "==> 更新 nginx 配置"
cp "$REPO_DIR/ops/nginx/heuesta.cn.conf" /etc/nginx/sites-available/heuesta.cn
ln -sf /etc/nginx/sites-available/heuesta.cn /etc/nginx/sites-enabled/heuesta.cn
nginx -t
systemctl reload nginx

echo "==> 安装/刷新每日备份定时器"
cp "$REPO_DIR/ops/heuesta-backup.service" "$REPO_DIR/ops/heuesta-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now heuesta-backup.timer >/dev/null 2>&1 || true

echo "==> 部署完成：https://heuesta.cn"
