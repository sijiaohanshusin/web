#!/usr/bin/env bash
# 异地备份拉取脚本 —— 部署在实验室 Linux 虚拟机上，每日定时执行。
# 通过限权账号 backup-puller 从云服务器拉取全部备份（主站库/论坛库/上传文件/论坛附件），
# 本地保留 30 天（云端只保留 7 天），实现"数据落地本地"。
#
# 依赖：云服务器已创建 backup-puller 账号并配置 rrsync 只读限制（见维护手册）。
set -euo pipefail

REMOTE="backup-puller@123.57.6.128"
LOCAL_DIR="$HOME/heuesta-backups"
LOG="$LOCAL_DIR/pull.log"
KEEP_DAYS=30

mkdir -p "$LOCAL_DIR/cloud"

{
    echo "===== $(date '+%F %T') 开始拉取 ====="
    # rrsync 限定了远端根目录即 /srv/heuesta/backups，因此源路径写 ':/'
    rsync -az --timeout=120 "$REMOTE:/" "$LOCAL_DIR/cloud/"

    echo "--- 清理本地 ${KEEP_DAYS} 天前的备份 ---"
    find "$LOCAL_DIR/cloud" -type f -mtime +$KEEP_DAYS -delete

    echo "--- 当前本地备份占用 ---"
    du -sh "$LOCAL_DIR/cloud"
    df -h "$LOCAL_DIR" | tail -1
    echo "===== $(date '+%F %T') 拉取完成 ====="
} >> "$LOG" 2>&1
