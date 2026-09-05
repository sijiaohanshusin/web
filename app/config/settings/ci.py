"""Disposable PostgreSQL CI settings. Not valid for production deployment."""
import os
from .dev import *  # noqa: F401,F403

if os.environ.get("HEUESTA_ISOLATED_CI") != "1":
    raise RuntimeError("CI settings require an explicitly isolated database")

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "heuesta_ci",
    "USER": "heuesta_ci",
    "PASSWORD": os.environ["CI_DB_PASSWORD"],
    "HOST": "127.0.0.1",
    "PORT": os.environ.get("CI_DB_PORT", "5432"),
    "TEST": {"NAME": "test_heuesta_ci"},
}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
BILIBILI_API_ENABLED = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
