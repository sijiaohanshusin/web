"""Dedicated local-only database for role walkthroughs, never production."""
import os
from .dev import *  # noqa: F401,F403

if os.environ.get("HEUESTA_BROWSER_AUDIT") != "1":
    raise RuntimeError("Browser audit settings must be explicitly enabled")
DATABASES["default"]["NAME"] = REPO_DIR / ".shots" / "roles.sqlite3"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
BILIBILI_API_ENABLED = False
