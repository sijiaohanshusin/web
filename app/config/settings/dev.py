"""
本地开发配置：SQLite + 本地内存缓存，无需任何外部服务。
运行：python manage.py runserver
"""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# 开发环境固定 SSO 测试密钥（生产用 .env 注入的强随机值）
NODEBB_JWT_SECRET = "dev-sso-secret-not-for-production"
