"""Run only against a separately provisioned disposable PostgreSQL container."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"
from django.conf import settings

if os.environ.get("SHOWCASE_ISOLATED_TEST") != "1":
    raise SystemExit("Set SHOWCASE_ISOLATED_TEST=1 only for an isolated disposable database.")
settings.DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": "showcase_test",
    "USER": "showcase_test", "PASSWORD": os.environ["TEST_DB_PASSWORD"],
    "HOST": os.environ.get("TEST_DB_HOST", "showcase-v3-pg"), "PORT": "5432",
    "TEST": {"NAME": "test_showcase_v3"},
}}
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
settings.BILIBILI_API_ENABLED = False
settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
import django
django.setup()
from django.test.runner import DiscoverRunner

raise SystemExit(bool(DiscoverRunner(verbosity=1, interactive=False).run_tests(
    ["showcase.test_concurrency", "showcase.test_editor_v3"]
)))
