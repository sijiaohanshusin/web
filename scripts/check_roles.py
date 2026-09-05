"""Real login and cross-role pages against a dedicated local audit database."""
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
from shoot import DevServer, do_login, port_open
from playwright.sync_api import sync_playwright

PORT = 8807
OUT = ROOT / '.shots' / 'roles'


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import User
    from core.test_role_contracts import ROUTES, expected_status, make_roles

    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots' / 'roles.sqlite3'
    assert not port_open(PORT), 'Refuse to reuse an unknown server'
    OUT.mkdir(parents=True, exist_ok=True)
    call_command('migrate', verbosity=0)
    password = 'RoleAudit-Only-2026!'
    users = make_roles('audit-' + uuid.uuid4().hex[:8], password)
    checks, failures, errors = [], [], []
    try:
        with DevServer(PORT), sync_playwright() as pw:
            browser = pw.chromium.launch()
            base = f'http://127.0.0.1:{PORT}'
            for role, user in users.items():
                ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                if user and user.is_active:
                    do_login(ctx, base, f'{user.username}:{password}')
                elif user:
                    page = ctx.new_page()
                    page.goto(base + '/accounts/login/')
                    page.locator('[name=username]').fill(user.username)
                    page.locator('[name=password]').fill(password)
                    page.locator('form button[type=submit]').click()
                    page.wait_for_load_state('domcontentloaded')
                    assert '/accounts/login/' in page.url, 'pending account must not authenticate'
                    page.close()
                for url, rule in ROUTES.items():
                    response = ctx.request.get(base + url, max_redirects=0)
                    expected = expected_status(role, rule)
                    result = {'role': role, 'url': url, 'expected': expected, 'actual': response.status}
                    checks.append(result)
                    if response.status != expected:
                        failures.append(result)
                    response.dispose()
                if role in {'member', 'officer', 'admin'}:
                    urls = ['/accounts/profile/', '/help/member/'] if role == 'member' else [
                        '/dashboard/', '/dashboard/members/', '/dashboard/news/', '/help/admin/',
                    ]
                    if role == 'admin':
                        urls += ['/dashboard/positions/', '/dashboard/site/']
                    page = ctx.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    for width in (1440, 390):
                        page.set_viewport_size({'width': width, 'height': 920})
                        for index, url in enumerate(urls):
                            assert page.goto(base + url).status == 200
                            page.evaluate('document.fonts.ready')
                            page.wait_for_timeout(350)
                            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
                            if overflow:
                                failures.append({'role': role, 'url': url, 'width': width, 'error': 'horizontal overflow'})
                            page.screenshot(path=str(OUT / f'{role}-{index}-{width}.png'), full_page=True)
                ctx.close()
            browser.close()
    finally:
        User.objects.filter(pk__in=[u.pk for u in users.values() if u]).delete()
        (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'failures': failures, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not failures, failures
    assert not errors, errors
    print(f'PASS: {len(checks)} role/path checks, 24 responsive walkthrough screenshots; only local fixtures used')


if __name__ == '__main__':
    run()
