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

for key in GMAIL_IMAP_USER GMAIL_APP_PASSWORD; do
    if ! grep -Eq "^${key}=.+" "$ENV_FILE"; then
        echo "警告：$ENV_FILE 尚未配置 $key，公共邮箱版块会部署，但 Gmail IMAP 同步保持未连接状态" >&2
    fi
done

install -d -m 755 /srv/heuesta/forum/config /srv/heuesta/forum/uploads
install -m 644 "$FORUM_DIR/groups-v2.js" /srv/heuesta/forum/config/groups-v2.js
install -m 644 "$FORUM_DIR/categories-v2.js" /srv/heuesta/forum/config/categories-v2.js
install -m 644 "$FORUM_DIR/internal-board.js" /srv/heuesta/forum/config/internal-board.js
install -m 644 "$FORUM_DIR/theme-v2.js" /srv/heuesta/forum/config/theme-v2.js
install -m 644 "$FORUM_DIR/formal-release.js" /srv/heuesta/forum/config/formal-release.js
install -m 644 "$FORUM_DIR/banner.webp" /srv/heuesta/forum/config/banner.webp
chown -R 1000:1000 /srv/heuesta/forum

echo "==> 构建论坛镜像"
$COMPOSE build

echo "==> 启动论坛"
$COMPOSE up -d

wait_for_forum() {
    echo "==> 等待论坛就绪（首次启动需初始化数据库并构建前端，约 2-5 分钟）"
    for i in $(seq 1 150); do
        if curl -fsS -o /dev/null http://127.0.0.1:4567/; then
            echo "论坛已就绪"
            return 0
        fi
        if [ "$i" = 150 ]; then
            echo "论坛启动超时，查看日志：$COMPOSE logs forum" >&2
            return 1
        fi
        sleep 4
    done
}

wait_for_forum

echo "==> 同步正式版用户组与私密版块权限"
$COMPOSE exec -T forum node /opt/config/groups-v2.js
$COMPOSE exec -T forum node /opt/config/categories-v2.js
$COMPOSE exec -T forum node /opt/config/internal-board.js

echo "==> 启用公共邮箱插件并重建 NodeBB 模板"
$COMPOSE exec -T forum ./nodebb activate nodebb-plugin-heuesta-mailbox
# 插件没有前端 JS/CSS，只选择性构建模板，避免小规格服务器执行完整 webpack 构建。
$COMPOSE exec -T forum timeout --signal=TERM --kill-after=15s 120 ./nodebb build tpl
$COMPOSE restart forum
wait_for_forum

echo "==> 应用正式论坛主题并归档内测帖"
$COMPOSE exec -T forum node /opt/config/theme-v2.js
$COMPOSE exec -T forum node /opt/config/formal-release.js
$COMPOSE restart forum
wait_for_forum

if [ -f /etc/nginx/sites-available/bbs.heuesta.cn ]; then
    echo "==> nginx 配置已存在，跳过（如需更新请手动 cp ops/nginx/bbs.heuesta.cn.conf）"
else
    echo "==> 安装 nginx 配置"
    cp /opt/heuesta/web/ops/nginx/bbs.heuesta.cn.conf /etc/nginx/sites-available/bbs.heuesta.cn
    ln -sf /etc/nginx/sites-available/bbs.heuesta.cn /etc/nginx/sites-enabled/bbs.heuesta.cn
    nginx -t && systemctl reload nginx
fi

echo "==> 论坛部署完成"
