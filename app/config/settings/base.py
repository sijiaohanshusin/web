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
    "recruitment",
    "projects",
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
    # **这一条在运行时会被 django-simpleui 摘掉。**
    # simpleui 的 apps.py 在 ready() 里无条件 `settings.MIDDLEWARE.pop(index)`
    # 掉它（它的后台 UI 靠 iframe 开标签页，而 Django 默认 X_FRAME_OPTIONS='DENY'
    # 会把自己的 iframe 也挡掉）。后果是**整站都不发 X-Frame-Options** —— 登录页、
    # 注册表单、驾驶舱都能被任意站点套进 iframe，而这里看起来完全正常。
    # 所以这个头由 nginx 在 `location /` 里发（见 ops/nginx/heuesta.cn.conf），
    # 那一层 simpleui 碰不到。这一行留着是为了：simpleui 哪天不再摘它时，
    # 保护会自动回到 Django 这一侧。`DeployPerfContractTests` 钉住这件事的现状。
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.DynamicPagesNoCacheMiddleware",
    "accounts.sso.SsoCookieMiddleware",
]

# ---- 论坛账号互通（NodeBB session-sharing）----
# 未设置 NODEBB_JWT_SECRET 时 SSO 中间件不生效
NODEBB_JWT_SECRET = os.environ.get("NODEBB_JWT_SECRET", "")
SSO_COOKIE_NAME = "heuesta_sso"
SSO_COOKIE_DOMAIN: str | None = None  # prod 覆盖为 .heuesta.cn

# SAMEORIGIN 而不是 DENY：simpleui 的后台要能把自己的页面套进自己的 iframe。
# 真正发这个头的是 nginx（simpleui 摘掉了那个中间件，见上面 MIDDLEWARE 的注释）。
X_FRAME_OPTIONS = "SAMEORIGIN"
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

# B 站开放接口开关。关掉后 core.bilibili 的所有取数直接降级返回空，
# 页面照常渲染（首页粉丝数/精选视频区自动隐藏）。测试环境默认关闭，见 dev.py。
BILIBILI_API_ENABLED = True

# 单个上传文件最大 200MB（nginx 侧同样限制 client_max_body_size）
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o644
