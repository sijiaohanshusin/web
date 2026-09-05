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
from playwright.sync_api import sync_playwright, expect

PORT = 8807
OUT = ROOT / '.shots' / 'roles'


def check_medal_workflow(browser, ctx, base, users, password, medal, checks):
    """Exercise real forms and recipient notification without touching production."""
    from accounts.models import UserMedal
    from notify.models import Notification

    member = users['member']
    page = ctx.new_page()
    assert page.goto(base + '/dashboard/medals/').status == 200
    form = page.locator('form').filter(has=page.locator('[name=form][value=grant]'))
    form.locator('[name=medal_id]').select_option(str(medal.pk))
    form.locator('[name=user_id]').fill('不存在的演示成员')
    form.locator('[name=reason]').fill('仅用于隔离环境流程验收')
    form.get_by_role('button', name='授予', exact=True).click()
    expect(page.locator('body')).to_contain_text('没找到成员')
    expect(form.locator('[name=medal_id]')).to_have_value(str(medal.pk))
    expect(form.locator('[name=reason]')).to_have_value('仅用于隔离环境流程验收')
    assert not UserMedal.objects.filter(medal=medal).exists()
    checks.append({'task': 'medal invalid member retains form and does not grant'})

    form.locator('[name=user_id]').fill(member.student_id)
    for width, label in ((1440, 'desktop'), (390, 'mobile')):
        page.set_viewport_size({'width': width, 'height': 1000})
        page.evaluate('document.fonts.ready')
        panel = page.locator('.dash-panel').filter(has=page.locator('[name=form][value=grant]'))
        panel.screenshot(path=str(OUT / f'medal-grant-{label}.png'))
    form.get_by_role('button', name='授予', exact=True).click()
    expect(page.locator('body')).to_contain_text('已授予')
    assert UserMedal.objects.get(medal=medal).user_id == member.pk
    checks.append({'task': 'medal grant by student ID through mobile form'})

    form.locator('[name=medal_id]').select_option(str(medal.pk))
    form.locator('[name=user_id]').fill(member.username)
    form.get_by_role('button', name='授予', exact=True).click()
    expect(page.locator('body')).to_contain_text('该成员已拥有此勋章')
    notes = member.notifications.filter(kind=Notification.Kind.MEDAL)
    assert notes.count() == 1
    checks.append({'task': 'duplicate grant by username creates no duplicate notification'})
    page.close()

    recipient = browser.new_context(viewport={'width': 390, 'height': 920}, reduced_motion='reduce')
    try:
        do_login(recipient, base, f'{member.username}:{password}')
        page = recipient.new_page()
        assert page.goto(base + '/notify/').status == 200
        notice = page.locator('.ntf-item').filter(has_text=medal.name)
        expect(notice).to_have_count(1)
        notice.click()
        page.wait_for_url('**/accounts/profile/')
        assert notes.get().read_at is not None
        expect(page.locator('body')).to_contain_text(medal.name)
        checks.append({'task': 'recipient opens medal notification and sees profile award'})
    finally:
        recipient.close()


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import Medal, User
    from core.test_role_contracts import ROUTES, expected_status, make_roles

    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots' / 'roles.sqlite3'
    assert not port_open(PORT), 'Refuse to reuse an unknown server'
    OUT.mkdir(parents=True, exist_ok=True)
    call_command('migrate', verbosity=0)
    password = 'RoleAudit-Only-2026!'
    users = make_roles('audit-' + uuid.uuid4().hex[:8], password)
    users['member'].student_id = f'2026{uuid.uuid4().int % 1000000:06d}'
    users['member'].save(update_fields=['student_id'])
    medal = Medal.objects.create(name='隔离验收勋章-' + uuid.uuid4().hex[:8])
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
                if role == 'admin':
                    check_medal_workflow(browser, ctx, base, users, password, medal, checks)
                ctx.close()
            browser.close()
    finally:
        medal.delete()
        User.objects.filter(pk__in=[u.pk for u in users.values() if u]).delete()
        (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'failures': failures, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not failures, failures
    assert not errors, errors
    print(f'PASS: {len(checks)} role/path and workflow checks, 26 screenshots; only local fixtures used')


if __name__ == '__main__':
    run()
