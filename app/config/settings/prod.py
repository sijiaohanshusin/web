"""
生产配置：PostgreSQL + 数据库缓存，由 docker compose 注入环境变量。
必需环境变量：DJANGO_SECRET_KEY、POSTGRES_DB、POSTGRES_USER、POSTGRES_PASSWORD
"""
import os

from .base import *  # noqa: F401,F403

DEBUG = False

if not os.environ.get("DJANGO_SECRET_KEY"):
    raise RuntimeError("生产环境必须设置 DJANGO_SECRET_KEY 环境变量")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "heuesta.cn,www.heuesta.cn").split(",")
CSRF_TRUSTED_ORIGINS = [f"https://{h.strip()}" for h in ALLOWED_HOSTS if h.strip()]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# 数据库缓存：多个 gunicorn worker 共享（B站数据缓存等），内存占用为零
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# 静态文件带内容哈希文件名，配合 nginx/CDN 一年长缓存
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}

# 论坛 SSO Cookie 需要覆盖主域及 bbs 子域
SSO_COOKIE_DOMAIN = ".heuesta.cn"

# 反向代理（nginx / CDN）之后的 HTTPS 识别
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# 日志输出到 stdout，由 docker logs 收集
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
