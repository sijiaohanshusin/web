#!/usr/bin/env bash
# 每日备份：数据库 dump + 上传文件打包，保留 7 天
# 由 heuesta-backup.timer 自动触发；手动执行：sudo /opt/heuesta/web/ops/backup.sh
set -euo pipefail

BACKUP_DIR=/srv/heuesta/backups
ENV_FILE=/opt/heuesta/.env
COMPOSE="docker compose -f /opt/heuesta/web/ops/docker-compose.yml --env-file $ENV_FILE"
STAMP=$(date +%Y%m%d-%H%M%S)

# shellcheck disable=SC1090
. "$ENV_FILE"

# 755：容许 backup-puller（异地备份限权账号）经 rrsync 只读进入
install -d -m 755 "$BACKUP_DIR"

echo "==> 备份主站数据库"
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

echo "==> 备份论坛数据库"
if $COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='nodebb'" | grep -q 1; then
    $COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" nodebb | gzip > "$BACKUP_DIR/forum-db-$STAMP.sql.gz"
fi

echo "==> 备份上传文件"
tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C /srv/heuesta media

if [ -d /srv/heuesta/forum/uploads ]; then
    echo "==> 备份论坛附件"
    tar -czf "$BACKUP_DIR/forum-uploads-$STAMP.tar.gz" -C /srv/heuesta/forum uploads
fi

echo "==> 清理 7 天前的备份"
find "$BACKUP_DIR" -name "db-*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "forum-db-*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "media-*.tar.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "forum-uploads-*.tar.gz" -mtime +7 -delete

echo "==> 备份完成：$BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5
