#!/usr/bin/env bash
# MySQL 每日备份，保留最近 14 天。
# 安装：
#   mkdir -p /www/backup/andyouchat
#   cp deploy/backup.sh /www/backup/andyouchat/ && chmod +x /www/backup/andyouchat/backup.sh
# crontab：
#   10 3 * * * /www/backup/andyouchat/backup.sh >> /www/backup/andyouchat/backup.log 2>&1
#
# 注意：备份和数据库在同一台机器上，只是防手滑/误删。
# 生产上请再用宝塔计划任务或 rclone/ossutil 把 BACKUP_DIR 同步到对象存储。

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/www/server/chat_server}"
ENV_FILE="$PROJECT_DIR/deploy/.env"
BACKUP_DIR="${BACKUP_DIR:-/www/backup/andyouchat}"
CONTAINER="andyou-mysql"
KEEP_DAYS=14

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[$(date '+%F %T')] 找不到 $ENV_FILE" >&2
  exit 1
fi

read_env() {
  grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-
}

DB_NAME="$(read_env MYSQL_DATABASE)"
DB_USER="$(read_env MYSQL_USER)"
DB_PASS="$(read_env MYSQL_PASSWORD)"

if [[ -z "$DB_NAME" || -z "$DB_USER" || -z "$DB_PASS" ]]; then
  echo "[$(date '+%F %T')] $ENV_FILE 缺少 MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[$(date '+%F %T')] 容器 $CONTAINER 未运行，跳过备份" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date '+%Y%m%d-%H%M%S')"
OUT="$BACKUP_DIR/andyouchat-$STAMP.sql.gz"

# MYSQL_PWD 传密码，避免在进程列表里暴露
if docker exec -e MYSQL_PWD="$DB_PASS" "$CONTAINER" \
    mysqldump -u"$DB_USER" \
      --single-transaction --quick --skip-lock-tables \
      --default-character-set=utf8mb4 \
      "$DB_NAME" | gzip > "$OUT"; then
  SIZE="$(du -h "$OUT" | cut -f1)"
  echo "[$(date '+%F %T')] 备份完成 $OUT ($SIZE)"
else
  echo "[$(date '+%F %T')] 备份失败" >&2
  rm -f "$OUT"
  exit 1
fi

# 清理过期备份
find "$BACKUP_DIR" -name 'andyouchat-*.sql.gz' -type f -mtime +"$KEEP_DAYS" -print -delete

# 磁盘占用提示
echo "[$(date '+%F %T')] 当前备份占用：$(du -sh "$BACKUP_DIR" | cut -f1)"
