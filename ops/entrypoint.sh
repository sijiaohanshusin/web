#!/bin/sh
# 应用容器入口：等数据库就绪 -> 迁移 -> 建缓存表 -> 收集静态 -> 起 gunicorn
set -e

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os
import sys
import time

import psycopg

dsn = "host={h} port={p} dbname={d} user={u} password={w}".format(
    h=os.environ.get("POSTGRES_HOST", "db"),
    p=os.environ.get("POSTGRES_PORT", "5432"),
    d=os.environ["POSTGRES_DB"],
    u=os.environ["POSTGRES_USER"],
    w=os.environ["POSTGRES_PASSWORD"],
)
for attempt in range(60):
    try:
        psycopg.connect(dsn, connect_timeout=3).close()
        sys.exit(0)
    except Exception:
        time.sleep(2)
print("database not reachable", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] migrate..."
python manage.py migrate --noinput

echo "[entrypoint] createcachetable..."
python manage.py createcachetable

echo "[entrypoint] collectstatic..."
python manage.py collectstatic --noinput

echo "[entrypoint] starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
