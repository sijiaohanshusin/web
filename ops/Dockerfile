# HEU ESTA 官网应用镜像
# 构建上下文是仓库根目录：docker compose -f ops/docker-compose.yml build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

COPY app/requirements.txt .
RUN pip install -r requirements.txt

COPY app/ .
COPY ops/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app

USER appuser

ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_STATIC_ROOT=/app/staticfiles \
    DJANGO_MEDIA_ROOT=/app/media

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
