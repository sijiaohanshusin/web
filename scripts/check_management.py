"""Isolated browser journeys for first-use management and member profile tasks."""
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
from shoot import DevServer, do_login, port_open
from playwright.sync_api import sync_playwright, expect

OUT = ROOT / '.shots' / 'management'
PORT = 8813


def screenshot(page, locator, name):
    page.evaluate('document.fonts.ready')
    locator.screenshot(path=str(OUT / f'{name}.png'))
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')


def news_journey(browser, staff, readers, base, officer, checks):
    from django.utils import timezone
    from news.models import Post

    page = staff.new_page()
    page.goto(base + '/dashboard/news/new/')
    expect(page.get_by_role('button', name='保存公告', exact=True)).to_be_visible()
    title = '手册演示 迎新说明'
    body = '## 报名前请先阅读\n\n这是隔离环境的演示公告，不是正式招新通知。\n\n- 核对个人资料\n- 查看报名进度'
    page.locator('[name=body]').fill(body)
    page.locator('[name=is_published]').uncheck()
    page.locator('[name=published_at]').fill((timezone.localtime() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'))
    page.locator('[name=title]').fill(title)
    screenshot(page, page.locator('.news-form-panel'), 'news-draft-form')
    screenshot(page, page.locator('.form-group').filter(has=page.locator('[name=min_level]')), 'news-visibility')
    screenshot(page, page.locator('.form-group').filter(has=page.locator('[name=is_published]')), 'news-publish-switch')
    screenshot(page, page.locator('.news-form-actions'), 'news-save-actions')
    page.locator('[name=title]').fill('')
    # Bypass only native required validation to exercise server error recovery.
    page.locator('form').filter(has=page.locator('[name=body]')).evaluate('(form) => form.noValidate = true')
    page.get_by_role('button', name='保存公告', exact=True).click()
    expect(page.locator('.form-error')).not_to_have_count(0)
    expect(page.locator('[name=body]')).to_have_value(body)
    assert not Post.objects.filter(author=officer).exists()
    checks.append('invalid news form preserves input and creates nothing')

    page.locator('[name=title]').fill(title)
    page.locator('[name=min_level]').select_option('0')
    page.get_by_role('button', name='保存公告', exact=True).click()
    page.wait_for_url('**/dashboard/news/')
    expect(page.locator('body')).to_contain_text('已保存为未发布')
    post = Post.objects.get(author=officer)
    row = page.locator('tbody tr').filter(has_text=title)
    expect(row).to_contain_text('未发布 / 已下架')
    for ctx in readers.values():
        response = ctx.request.get(base + post.get_absolute_url())
        assert response.status == 403
        response.dispose()
    checks.append('unpublished announcement is blocked for every reader role')

    with page.expect_popup() as popup:
        row.get_by_role('link', name=title, exact=True).click()
    preview = popup.value
    expect(preview.locator('.news-article-body')).to_contain_text('报名前请先阅读')
    screenshot(preview, preview.locator('.news-article'), 'news-preview')
    preview.close()
    page.bring_to_front()
    checks.append('staff previews saved Markdown without publication')
    row.get_by_role('button', name='发布', exact=True).click()
    expect(page.locator('body')).to_contain_text('已重新发布')
    for ctx in readers.values():
        response = ctx.request.get(base + post.get_absolute_url())
        assert response.status == 200
        response.dispose()
    checks.append('public announcement becomes visible to guests recruits and members')

    row.get_by_role('link', name='编辑', exact=True).click()
    page.locator('[name=min_level]').select_option('3')
    page.get_by_role('button', name='保存修改', exact=True).click()
    for role, ctx in readers.items():
        response = ctx.request.get(base + post.get_absolute_url(), max_redirects=0)
        assert response.status == {'guest': 302, 'recruit': 403, 'member': 200}[role]
        response.dispose()
        response = ctx.request.get(base + '/news/')
        assert (title in response.text()) == (role == 'member')
        response.dispose()
    checks.append('member-only content disappears from guest and recruit lists and direct access')
    screenshot(page, page.locator('.dash-table-wrap'), 'news-member-only')
    row.get_by_role('button', name='下架', exact=True).click()
    response = readers['member'].request.get(base + post.get_absolute_url())
    assert response.status == 403
    response.dispose()
    post.refresh_from_db()
    assert not post.is_published
    checks.append('withdrawal immediately blocks a previously authorized reader')
    assert page.evaluate("sessionStorage.getItem('audit-transition')") is None
    checks.append('reduced-motion navigation never starts a cross-document transition')
    page.close()


def returning_journey(browser, staff, base, user, password, request, checks, errors):
    page = staff.new_page()
    member = browser.new_context(viewport={'width': 390, 'height': 920}, reduced_motion='reduce')
    member.on('page', lambda page: page.on('pageerror', lambda error: errors.append({'url': urlsplit(page.url).path, 'message': str(error)})))
    try:
        login = member.new_page()
        login.goto(base + '/accounts/login/')
        login.locator('[name=username]').fill(user.username)
        login.locator('[name=password]').fill(password)
        login.locator('form button[type=submit]').click()
        expect(login.locator('form button[type=submit]')).to_be_visible()
        assert '/accounts/login/' in login.url
        response = member.request.get(base + '/accounts/profile/', max_redirects=0)
        assert response.status == 302
        response.dispose()
        login.close()
        checks.append('unapproved returning account cannot log in')

        page.goto(base + '/dashboard/members/?tab=returning&q=' + user.username)
        form = page.locator(f'form[action="/dashboard/members/returning/{request.pk}/review/"]')
        form.locator('[name=role]').select_option('member')
        form.locator('[name=note]').fill('仅用于隔离环境手册验收')
        screenshot(page, form, 'returning-review')
        form.get_by_role('button', name='通过并激活').click()
        expect(page.locator('body')).to_contain_text('已恢复')
        user.refresh_from_db()
        request.refresh_from_db()
        assert user.is_active and user.member_level == 3 and not user.position_id
        assert request.status == 'approved'
        checks.append('review corrects requested role and activates member without management rights')

        do_login(member, base, f'{user.username}:{password}')
        profile = member.new_page()
        profile.goto(base + '/accounts/profile/edit/')
        profile.locator('[name=real_name]').fill('手册演示成员')
        profile.locator('[name=college]').select_option(label='信息与通信工程学院')
        profile.locator('[name=grade]').select_option('2024')
        profile.locator('[name=specialty]').select_option('custom')
        profile.locator('[name=specialty_custom]').fill('')
        profile.locator('[data-profile-save]').click()
        expect(profile.locator('body')).to_contain_text('选择自定义方向时请填写具体方向')
        expect(profile.locator('[name=real_name]')).to_have_value('手册演示成员')
        profile.locator('[name=specialty_custom]').fill('交互设计与电子制作')
        screenshot(profile, profile.locator('.form-group').filter(has=profile.locator('[name=specialty]')), 'profile-direction')
        screenshot(profile, profile.locator('#public-team'), 'profile-showcase-entry')
        profile.locator('[data-profile-save]').click()
        profile.wait_for_url('**/accounts/profile/')
        user.refresh_from_db()
        assert user.specialty_custom == '交互设计与电子制作'
        assert user.real_name == '手册演示成员'
        checks.append('mobile profile validation preserves input and saves custom direction')
        response = member.request.get(base + '/dashboard/')
        assert response.status == 403
        response.dispose()
        checks.append('profile edit and old-member approval do not grant management access')
    finally:
        member.close()
        page.close()


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import ReturningMembershipRequest, User
    from core.test_role_contracts import make_roles
    from news.models import Post

    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots' / 'roles.sqlite3'
    assert not port_open(PORT), 'Refuse to reuse an unknown server'
    OUT.mkdir(parents=True, exist_ok=True)
    call_command('migrate', verbosity=0)
    password = 'Local-Onboarding-Only-2026!'
    users = make_roles('journey-' + uuid.uuid4().hex[:8], password)
    returning = ReturningMembershipRequest.objects.create(user=users['pending'], requested_role='chair')
    checks, errors = [], []
    try:
        with DevServer(PORT), sync_playwright() as pw:
            browser = pw.chromium.launch()
            base = f'http://127.0.0.1:{PORT}'
            contexts = {}
            for role in ('officer', 'guest', 'recruit', 'member'):
                ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                ctx.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
                ctx.on('page', lambda page: page.on('pageerror', lambda error: errors.append({'url': urlsplit(page.url).path, 'message': str(error), 'stack': error.stack})))
                ctx.add_init_script("window.addEventListener('pagereveal', e => { if(e.viewTransition) sessionStorage.setItem('audit-transition', 'started'); });")
                if users[role]:
                    do_login(ctx, base, f'{users[role].username}:{password}')
                contexts[role] = ctx
            news_journey(browser, contexts['officer'], {r: contexts[r] for r in ('guest', 'recruit', 'member')}, base, users['officer'], checks)
            returning_journey(browser, contexts['officer'], base, users['pending'], password, returning, checks, errors)
            for audience in ('recruit', 'member', 'admin'):
                page = contexts['officer' if audience == 'admin' else 'guest'].new_page()
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 920})
                    page.goto(base + f'/help/{audience}/')
                    steps = page.locator('.hc-onboarding')
                    steps.locator('summary').focus()
                    page.keyboard.press('Enter')
                    expect(steps).to_have_attribute('open', '')
                    expect(steps.locator('a[href="/help/member/profile/"]')).to_be_visible()
                    expect(steps.locator('a[href="/help/admin/settings/"]')).to_have_count(0)
                    screenshot(page, steps, f'onboarding-{audience}-{width}')
                    checks.append(f'{audience} onboarding {width}: keyboard expansion, profile step, permission filtering')
                page.close()
            for ctx in contexts.values():
                ctx.close()
            browser.close()
    finally:
        Post.objects.filter(author_id__in=[u.pk for u in users.values() if u]).delete()
        User.objects.filter(pk__in=[u.pk for u in users.values() if u]).delete()
        (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, errors
    print(f'PASS: {len(checks)} management/member workflow checks, local fake records cleaned')


if __name__ == '__main__':
    run()
