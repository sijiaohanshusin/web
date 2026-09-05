"""Capture current registration fields locally; never submit or send an email."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'app')]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
from shoot import DevServer, port_open
from playwright.sync_api import sync_playwright, expect


def run():
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', verbosity=0)
    assert not port_open(8810)
    out = ROOT / 'app/helpcenter/assets'
    with DevServer(8810), sync_playwright() as pw:
        browser = pw.chromium.launch()
        for channel in ('new', 'returning'):
            for width in (1440, 390):
                ctx = browser.new_context(viewport={'width': width, 'height': 1000}, reduced_motion='reduce')
                page = ctx.new_page()
                page.goto(f'http://127.0.0.1:8810/accounts/register/{channel}/')
                page.locator('#id_real_name').fill('手册演示成员')
                page.locator('#id_student_id').fill('2026999999')
                page.locator('#id_college').select_option(index=1)
                page.locator('#id_grade').select_option(index=1)
                page.locator('#id_specialty').select_option('software')
                if channel == 'returning':
                    page.locator('#id_requested_role').select_option(index=1)
                page.locator('[data-step-next]').click()
                page.locator('#id_email').fill('manual@example.invalid')
                page.locator('#id_code').fill('000000')
                page.locator('#id_phone').fill('13900000000')
                page.locator('[data-step-next]').click()
                expect(page.locator('#id_username')).to_be_visible()
                page.locator('#id_username').fill('林序.dev')
                page.evaluate('document.fonts.ready')
                page.wait_for_timeout(250)
                # Each crop is an actual form region. Passwords and contact
                # summaries are outside this crop, so no masking can hide UI.
                field = page.locator('#id_username').locator('..')
                field.screenshot(path=str(out / f'registration-username-{channel}-{width}.png'))
                ctx.close()
        browser.close()


if __name__ == '__main__':
    run()
