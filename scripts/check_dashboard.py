"""Responsive, keyboard and no-script checks for local-only dashboard tables."""
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

from playwright.sync_api import expect, sync_playwright
from shoot import DevServer, do_login, port_open

PORT = 8812
OUT = ROOT / '.shots' / 'dashboard'


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import User
    from core.test_role_contracts import make_roles

    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots' / 'roles.sqlite3'
    assert not port_open(PORT), 'Refuse to reuse an unknown server'
    OUT.mkdir(parents=True, exist_ok=True)
    call_command('migrate', verbosity=0)
    password = 'DashboardAudit-Only-2026!'
    prefix = 'table-' + uuid.uuid4().hex[:8]
    users = make_roles(prefix, password)
    ids = [user.pk for user in users.values() if user]
    User.objects.filter(pk__in=ids).update(college='信息与通信工程学院', grade='2024')
    checks, errors = [], []
    try:
        with DevServer(PORT), sync_playwright() as pw:
            browser = pw.chromium.launch()
            base = f'http://127.0.0.1:{PORT}'
            ctx = browser.new_context(reduced_motion='reduce')
            do_login(ctx, base, f'{users["admin"].username}:{password}')
            page = ctx.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            url = base + '/dashboard/members/?tab=all&q=' + prefix
            for width in (390, 320, 768, 1024, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.goto(url).status == 200
                page.evaluate('document.fonts.ready')
                table = page.locator('.dash-table-wrap')
                scrollable = table.evaluate('(el) => el.scrollWidth > el.clientWidth + 1')
                controls = page.locator('.dash-scroll-controls')
                if scrollable:
                    expect(controls).to_be_visible(timeout=2000)
                    expect(table).to_have_attribute('tabindex', '0')
                    next_button = controls.get_by_role('button', name='向右查看表格')
                    previous = controls.get_by_role('button', name='向左查看表格')
                    expect(previous).to_be_disabled()
                    checkbox = table.locator(f'input[name=ids][value="{users["member"].pk}"]')
                    checkbox.check()
                    next_button.click()
                    page.wait_for_function('document.querySelector(".dash-table-wrap").scrollLeft > 0')
                    expect(previous).to_be_enabled()
                    table.focus()
                    page.keyboard.press('End')
                    expect(next_button).to_be_disabled()
                    expect(checkbox).to_be_checked()
                    key = table.locator('tbody [data-sticky-key]').first
                    left = key.bounding_box()['x']
                    assert table.bounding_box()['x'] - 1 <= left <= table.bounding_box()['x'] + 4
                    page.screenshot(path=str(OUT / f'members-end-{width}.png'), full_page=True)
                    page.keyboard.press('Home')
                    expect(previous).to_be_disabled()
                    page.keyboard.press('ArrowRight')
                    page.wait_for_function('document.querySelector(".dash-table-wrap").scrollLeft > 0')
                    checks.append(f'{width}: scroll buttons, keyboard, sticky identity and selection retention')
                else:
                    expect(controls).to_be_hidden()
                    assert table.get_attribute('tabindex') is None
                    checks.append(f'{width}: fitting table has no unnecessary controls')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(OUT / f'members-{width}.png'), full_page=True)

            # Disabling JavaScript must not trap content or hide existing inputs.
            plain = browser.new_context(java_script_enabled=False, storage_state=ctx.storage_state(),
                                        viewport={'width': 320, 'height': 920})
            page = plain.new_page()
            assert page.goto(url).status == 200
            expect(page.get_by_text('窄屏下可左右滑动表格查看其余列。')).to_be_visible()
            expect(page.locator(f'input[name=ids][value="{users["member"].pk}"]')).to_be_visible()
            checks.append('no JavaScript: native table and guidance remain available')
            plain.close()
            ctx.close()
            browser.close()
    finally:
        User.objects.filter(pk__in=ids).delete()
        (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, errors
    print(f'PASS: {len(checks)} dashboard layout/interaction checks; isolated fixtures removed')


if __name__ == '__main__':
    run()
