#!/usr/bin/env bash
# 论坛部署脚本（与主站 deploy.sh 完全独立，互不影响）
# 用法：sudo /opt/heuesta/web/ops/forum/deploy-forum.sh
set -euo pipefail

FORUM_DIR=/opt/heuesta/web/ops/forum
ENV_FILE=/opt/heuesta/forum.env
COMPOSE="docker compose -f $FORUM_DIR/docker-compose.yml --env-file $ENV_FILE"

if [ ! -f "$ENV_FILE" ]; then
    echo "缺少 $ENV_FILE（NODEBB_DB_PASSWORD / NODEBB_JWT_SECRET / NODEBB_ADMIN_PASSWORD）" >&2
    exit 1
fi

install -d -m 755 /srv/heuesta/forum/config /srv/heuesta/forum/uploads
chown -R 1000:1000 /srv/heuesta/forum

echo "==> 构建论坛镜像"
$COMPOSE build

echo "==> 启动论坛"
$COMPOSE up -d

echo "==> 等待论坛就绪（首次启动需初始化数据库并构建前端，约 2-5 分钟）"
for i in $(seq 1 150); do
    if curl -fsS -o /dev/null http://127.0.0.1:4567/; then
        echo "论坛已就绪"
        break
    fi
    if [ "$i" = 150 ]; then
        echo "论坛启动超时，查看日志：$COMPOSE logs forum" >&2
        exit 1
    fi
    sleep 4
done

if [ -f /etc/nginx/sites-available/bbs.heuesta.cn ]; then
    echo "==> nginx 配置已存在，跳过（如需更新请手动 cp ops/nginx/bbs.heuesta.cn.conf）"
else
    echo "==> 安装 nginx 配置"
    cp /opt/heuesta/web/ops/nginx/bbs.heuesta.cn.conf /etc/nginx/sites-available/bbs.heuesta.cn
    ln -sf /etc/nginx/sites-available/bbs.heuesta.cn /etc/nginx/sites-enabled/bbs.heuesta.cn
    nginx -t && systemctl reload nginx
fi

echo "==> 论坛部署完成"
