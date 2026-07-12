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

install -d -m 750 "$BACKUP_DIR"

echo "==> 备份数据库"
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

echo "==> 备份上传文件"
tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C /srv/heuesta media

echo "==> 清理 7 天前的备份"
find "$BACKUP_DIR" -name "db-*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "media-*.tar.gz" -mtime +7 -delete

echo "==> 备份完成：$BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5
