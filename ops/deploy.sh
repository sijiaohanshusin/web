#!/usr/bin/env bash
# HEU ESTA 官网部署脚本（在服务器上执行）
# 用法：sudo /opt/heuesta/web/ops/deploy.sh
# 幂等：可重复执行；每次执行 = 拉最新代码 + 重建容器 + 同步学习中心 + 重载 nginx
set -euo pipefail

REPO_DIR=/opt/heuesta/web
ENV_FILE=/opt/heuesta/.env
COMPOSE="docker compose -f $REPO_DIR/ops/docker-compose.yml --env-file $ENV_FILE"

if [ ! -f "$ENV_FILE" ]; then
    echo "缺少 $ENV_FILE，请先从 ops/env.example 复制并填写" >&2
    exit 1
fi

echo "==> 拉取最新代码"
cd "$REPO_DIR"
git fetch origin main
git reset --hard origin/main

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

echo "==> 部署完成：https://heuesta.cn"
