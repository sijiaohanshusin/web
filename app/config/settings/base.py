"""
HEU ESTA 官网 - 基础配置（dev.py / prod.py 均继承本文件）
"""
import os
from pathlib import Path

# app/ 目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 仓库根目录（learn/ 学习中心所在处）
REPO_DIR = BASE_DIR.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "simpleui",  # Django Admin 主题，必须在 admin 之前
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "accounts",
    "files",
    "dashboard",
    "notify",
    "news",
    "events",
    "points",
]

# ---- simpleui（Admin 美化）----
SIMPLEUI_HOME_INFO = False       # 关闭首页 simpleui 宣传卡片
SIMPLEUI_ANALYSIS = False        # 禁用使用统计外联
SIMPLEUI_STATIC_OFFLINE = True   # 全部静态资源本地化，不请求外网
SIMPLEUI_LOGO = "/static/img/logo.png"
SIMPLEUI_DEFAULT_THEME = "layui.css"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.DynamicPagesNoCacheMiddleware",
    "accounts.sso.SsoCookieMiddleware",
]

# ---- 论坛账号互通（NodeBB session-sharing）----
# 未设置 NODEBB_JWT_SECRET 时 SSO 中间件不生效
NODEBB_JWT_SECRET = os.environ.get("NODEBB_JWT_SECRET", "")
SSO_COOKIE_NAME = "heuesta_sso"
SSO_COOKIE_DOMAIN: str | None = None  # prod 覆盖为 .heuesta.cn
FORUM_URL = os.environ.get("FORUM_URL", "https://bbs.heuesta.cn")

# ---- 邮件（验证码 / 找回密码 / 审核通知）----
# 未配置 EMAIL_HOST_USER 时，dev 用控制台后端；prod 缺省会拒绝发码
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "465"))
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "1") == "1"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", f"HEU ESTA <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "webmaster@localhost"
)
VERIFICATION_CODE_TTL = 600          # 验证码有效期（秒）
VERIFICATION_RESEND_COOLDOWN = 60    # 重发冷却（秒）
VERIFICATION_DAILY_LIMIT = 10        # 单邮箱每日发码上限

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
                "dashboard.context_processors.pending_members",
                "notify.context_processors.unread",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# 自定义用户模型（会员系统的地基，切勿更改）
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 单个上传文件最大 200MB（nginx 侧同样限制 client_max_body_size）
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o644
