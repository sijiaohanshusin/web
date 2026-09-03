"""Compatibility check entry point for the redesigned member showcase.
Run: python scripts/check_team.py [--keep]
--keep also creates local fictional samples for manual browser verification.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ["BILIBILI_API_ENABLED"] = "0"

import django
from django.conf import settings
from django.core.management import call_command
from django.test.runner import DiscoverRunner

django.setup()
if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    raise SystemExit("This helper is restricted to local DEBUG + SQLite.")
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
failed = DiscoverRunner(verbosity=1).run_tests([
    "showcase", "accounts.tests.TeamQuerysetTests",
    "accounts.tests.TeamWallViewTests", "accounts.tests.ProfileTeamOptInTests",
    "accounts.test_positions", "dashboard.test_position_picker",
])
if failed:
    raise SystemExit(1)
if "--keep" in sys.argv:
    call_command("migrate", interactive=False)
    call_command("seed_showcase_demo")
    print("Start the local server; inspect /team/ and /accounts/showcase/ at desktop/mobile sizes.")
