"""Disposable local screenshots for the September 6 manual revision."""
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'scripts')]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
from shoot import DevServer, port_open


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.files.uploadedfile import SimpleUploadedFile
    from accounts.models import User
    from core.models import Feedback, FeedbackReply
    from showcase.services import add_asset, get_showcase
    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots/roles.sqlite3'
    assert not port_open(8816)
    call_command('migrate', verbosity=0)
    username = 'manual-local-' + uuid.uuid4().hex[:8]
    user = User.objects.create_user(username=username, password='ManualLocal-Only-2026!',
        real_name='手册演示成员', member_level=3, grade='2024', specialty='hardware')
    fb = None
    try:
        get_showcase(user)
        for name in ('signal', 'soldering'):
            path = ROOT / 'app/showcase/demo_assets' / (name + '.png')
            add_asset(user, SimpleUploadedFile(name + '.png', path.read_bytes(), content_type='image/png'))
        fb = Feedback.objects.create(user=user, page='/help/', content='手册演示：手机查看帮助时，希望步骤更直观。仅用于本地操作示例。')
        FeedbackReply.objects.create(feedback=fb, author=user, content='补充：这是虚构演示对话，不是正式故障。')
        print(f'LOCAL ONLY http://127.0.0.1:8816 login={username} password=ManualLocal-Only-2026!', flush=True)
        with DevServer(8816):
            while True:
                time.sleep(1)
    finally:
        # Only the account created by this process; never reuse a real member.
        if fb is not None:
            fb.delete()
        user.delete()


if __name__ == '__main__':
    run()
