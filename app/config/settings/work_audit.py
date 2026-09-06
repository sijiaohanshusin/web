"""Isolated local works-flow audit, never reuse member or production data."""
import os
from .dev import *  # noqa: F401,F403

if os.environ.get('HEUESTA_WORK_AUDIT') != '1':
    raise RuntimeError('Works audit must be explicitly enabled')
DATABASES['default']['NAME'] = REPO_DIR / '.shots' / 'member-works-audit.sqlite3'
MEDIA_ROOT = REPO_DIR / '.shots' / 'member-works-media'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
BILIBILI_API_ENABLED = False
