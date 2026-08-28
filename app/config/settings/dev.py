"""
本地开发配置：SQLite + 本地内存缓存，无需任何外部服务。
运行：python manage.py runserver
"""
import os
import sys

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

# 跑测试时不碰 B 站接口：外网往返在 CI/离线环境下结果不可复现，
# 且 412 风控会把日志刷满。需要验证真实取数时用 runserver。
TESTING = "test" in sys.argv
# 也允许用环境变量关掉：scripts/shoot.py 起开发服务器时会置 0。
# 原因是 dev 用 LocMem 缓存，每次新起进程都是冷缓存，首页要同步等三个
# B 站接口；赶上限流就是 6 秒超时 ×3，截图循环直接被拖死。
BILIBILI_API_ENABLED = (
    not TESTING and os.environ.get("BILIBILI_API_ENABLED", "1") != "0"
)

if TESTING:
    # 整套测试大量创建用户，PBKDF2 的迭代次数是唯一的耗时大头
    # （实测 267s -> 30s）。只在测试期生效，不影响 runserver 与生产。
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
