#!/bin/sh
# NodeBB 容器入口：首次启动执行免交互 setup（建库表 + 管理员 + 构建前端资源），
# 之后每次启动直接复用持久化的 config.json。
set -e
cd /usr/src/app

CONFIG_DIR=/opt/config
CONFIG="$CONFIG_DIR/config.json"

if [ ! -f "$CONFIG" ]; then
    echo "[forum] first run - unattended setup"
    NODEBB_SECRET=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
    ./nodebb setup "{
        \"url\": \"${NODEBB_URL}\",
        \"secret\": \"${NODEBB_SECRET}\",
        \"database\": \"postgres\",
        \"postgres:host\": \"${NODEBB_DB_HOST:-db}\",
        \"postgres:port\": 5432,
        \"postgres:username\": \"nodebb\",
        \"postgres:password\": \"${NODEBB_DB_PASSWORD}\",
        \"postgres:database\": \"nodebb\",
        \"postgres:ssl\": false,
        \"admin:username\": \"admin\",
        \"admin:password\": \"${NODEBB_ADMIN_PASSWORD}\",
        \"admin:password:confirm\": \"${NODEBB_ADMIN_PASSWORD}\",
        \"admin:email\": \"${NODEBB_ADMIN_EMAIL:-admin@heuesta.cn}\"
    }"
    cp config.json "$CONFIG"
    echo "[forum] setup complete, config persisted"
else
    echo "[forum] using existing config"
    cp "$CONFIG" ./config.json
fi

exec node loader.js --no-silent --no-daemon
