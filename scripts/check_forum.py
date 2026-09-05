"""Real Django login -> NodeBB session sharing, posting and mailbox access, CI only."""
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
os.environ['FORUM_URL'] = 'http://127.0.0.1:4567'
from shoot import DevServer, do_login, port_open
from playwright.sync_api import sync_playwright, expect

OUT = ROOT / '.shots' / 'forum-evidence'
APP = ROOT / '.shots' / 'forum-runtime'
BASE = 'http://127.0.0.1:8814'
FORUM = 'http://127.0.0.1:4567'


def safe_startup_diagnostic(config):
    text = (OUT / 'server.private.log').read_text(errors='replace')[-7000:]
    for secret in (config.get('secret'), config['postgres'].get('password'), 'dev-sso-secret-not-for-production'):
        if secret:
            text = text.replace(secret, '[redacted]')
    text = re.sub(r'eyJ[A-Za-z0-9_.-]+', '[redacted-jwt]', text)
    text = '\n'.join(line for line in text.splitlines() if not re.search(r'cookie|token|password|secret', line, re.I))
    return text


def capture(page, name):
    page.evaluate('document.fonts.ready')
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')


def api(page, path, method='GET', body=None):
    return page.evaluate('''async ({path, method, body}) => {
      const response = await fetch(path, {method, headers: {
        'Content-Type': 'application/json', 'x-csrf-token': config.csrf_token,
      }, ...(body ? {body: JSON.stringify(body)} : {})});
      return {status: response.status, text: await response.text()};
    }''', {'path': path, 'method': method, 'body': body})


def submit_and_review(page, admin, api_path, checks, name):
    with page.expect_response(lambda r: urlsplit(r.url).path == api_path and r.request.method == 'POST') as pending:
        page.locator('[component="composer"] [data-action="post"]:visible').click()
    response = pending.value
    # NodeBB 4.14 returns 202 for a queued topic, but 200 for a queued reply.
    assert response.status == (202 if api_path == '/api/v3/topics' else 200), response.text()
    data = response.json()['response']
    assert data.get('queued'), 'Fresh accounts must follow the actual default moderation queue'
    checks.append(f'{name}: submission enters review rather than silently disappearing')
    admin.goto(FORUM + '/post-queue')
    row = admin.locator(f'[data-id="{data["id"]}"]').first
    expect(row).to_be_visible()
    capture(admin, f'forum-{name}-review')
    endpoint = f'/api/v3/posts/queue/{data["id"]}'
    with admin.expect_response(lambda r: urlsplit(r.url).path == endpoint and r.request.method == 'POST') as accepted:
        row.locator('[data-action="accept"]').click()
    assert accepted.value.status == 200, accepted.value.text()
    post = accepted.value.json()['response']['post']
    checks.append(f'{name}: forum administrator approves through the actual review page')
    return f'{FORUM}/topic/{post["tid"]}'


def run():
    assert os.environ.get('HEUESTA_FORUM_AUDIT') == '1'
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert not os.environ.get('GMAIL_APP_PASSWORD') and not os.environ.get('GMAIL_OAUTH_CLIENT_SECRET')
    assert not port_open(8814) and not port_open(4567), 'Do not reuse existing services'
    config = json.loads((APP / 'config.json').read_text())
    assert config['url'] == FORUM and config['postgres']['host'] == '127.0.0.1'
    assert config['postgres']['database'] == 'heuesta_forum_ci'
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import User
    from core.test_role_contracts import make_roles
    assert settings.DEBUG and Path(settings.DATABASES['default']['NAME']) == ROOT / '.shots/roles.sqlite3'
    call_command('migrate', verbosity=0)
    password = secrets.token_urlsafe(28)
    users = make_roles('forum-audit', password)
    for role, user in users.items():
        if user:
            user.email = 'admin@example.invalid' if role == 'admin' else f'audit-{role}@example.invalid'
            user.save(update_fields=['email'])
    # Intentionally exercise Unicode usernames through real SSO, not a fabricated JWT.
    users['member'].username = '手册演示.成员'
    users['member'].save(update_fields=['username'])
    checks, errors = [], []
    fixture_file = OUT / 'fixture.private.json'
    env = os.environ | {'NODE_ENV': 'production', 'HEUESTA_FORUM_FIXTURE': str(fixture_file)}
    proc = None
    try:
        with (OUT / 'server.private.log').open('w') as log:
            proc = subprocess.Popen(['node', 'app.js'], cwd=APP, env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(120):
                if proc.poll() is not None:
                    raise RuntimeError('Forum startup failed:\n' + safe_startup_diagnostic(config))
                if fixture_file.exists() and port_open(4567):
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Isolated forum readiness timeout:\n' + safe_startup_diagnostic(config))
            fixture = json.loads(fixture_file.read_text())
            checks.extend(fixture['checks'])
            with DevServer(8814), sync_playwright() as p:
                browser = p.chromium.launch()
                contexts, pages = {}, {}
                try:
                    for role in ('guest', 'recruit', 'preparatory', 'member', 'officer', 'admin'):
                        ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                        contexts[role] = ctx
                        ctx.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
                        ctx.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
                        if role != 'guest':
                            do_login(ctx, BASE, f'{users[role].username}:{password}')
                        cookie = next((c for c in ctx.cookies() if c['name'] == 'heuesta_sso'), None)
                        assert bool(cookie) == (role not in ('guest', 'recruit')), role
                        page = ctx.new_page()
                        pages[role] = page
                        page.goto(FORUM + '/categories')
                        page.wait_for_function('window.app && app.user && window.config')
                        uid = page.evaluate('Number(app.user.uid)')
                        assert (uid > 0) == (role not in ('guest', 'recruit')), role
                        checks.append(f'{role}: real main-site login and forum SSO eligibility')
                        result = api(page, f"/api/category/{fixture['mailboxCid']}")
                        assert (result['status'] == 200) == (role in ('member', 'officer', 'admin')), (role, result['status'])
                        result = api(page, f"/api/topic/{fixture['mailboxTid']}")
                        assert (result['status'] == 200) == (role in ('member', 'officer', 'admin')), role
                        listing = api(page, '/api/categories')
                        assert ('公共邮箱' in listing['text']) == (role in ('member', 'officer', 'admin')), role
                        preview = api(page, f"/api/heuesta-mailbox/preview/{fixture['previewToken']}")
                        assert preview['status'] == (200 if role in ('member', 'officer', 'admin') else 404), role
                        if preview['status'] == 200:
                            assert '<script' not in preview['text'] and 'https://tracking.invalid' not in preview['text']
                        checks.append(f'{role}: mailbox listing topic API and HTML preview privacy')
                    member = pages['member']
                    admin = pages['admin']
                    assert admin.evaluate('app.user.isAdmin')
                    assert not pages['officer'].evaluate('app.user.isAdmin'), 'Main-site rank must not grant NodeBB administration'
                    checks.append('forum administration remains separately granted')
                    # Verify revocation before the writing journey, then restore only
                    # this disposable member so the remaining checks still run.
                    users['member'].member_level = 2
                    users['member'].save(update_fields=['member_level'])
                    main = contexts['member'].new_page()
                    main.goto(BASE + '/accounts/profile/')
                    member.goto(FORUM + '/categories')
                    result = api(member, f"/api/topic/{fixture['mailboxTid']}")
                    if result['status'] == 200:
                        errors.append('SSO: existing forum session retained mailbox access after downgrade')
                    else:
                        checks.append('existing forum session synchronizes downgrade on next forum page load')
                    main.locator('form[action$="/accounts/logout/"] button').click()
                    member.goto(FORUM + '/categories')
                    member.wait_for_function('window.app && app.user')
                    if member.evaluate('Number(app.user.uid)') != 0:
                        errors.append('SSO: forum retained login after main-site logout')
                    else:
                        checks.append('main-site logout clears the forum identity on next page load')
                    users['member'].member_level = 3
                    users['member'].save(update_fields=['member_level'])
                    do_login(contexts['member'], BASE, f'{users["member"].username}:{password}')
                    main.close()
                    member.goto(FORUM + f"/category/{fixture['discussionCid']}")
                    member.locator('[component="category/post"]').click()
                    member.locator('[component="composer"] input.title').fill('手册演示：第一次发帖')
                    member.locator('[component="composer"] textarea.write').fill('## 我想交流的内容\n\n这是隔离环境中的演示帖子，请不要用于正式通知。')
                    capture(member, 'forum-compose')
                    topic_url = submit_and_review(member, admin, '/api/v3/topics', checks, 'topic')
                    member.goto(topic_url)
                    expect(member.locator('[component="post/content"]').first).to_contain_text('隔离环境中的演示帖子')
                    checks.append('member creates a real topic through the composer')
                    reply = pages['preparatory']
                    reply.goto(topic_url)
                    reply.locator('[component="topic/reply"]:visible').first.click()
                    reply.locator('[component="composer"] textarea.write').fill('这是预备会员的演示回复，发布后应当显示在主题中。')
                    capture(reply, 'forum-reply-compose')
                    tid = topic_url.rsplit('/', 1)[-1]
                    submit_and_review(reply, admin, f'/api/v3/topics/{tid}', checks, 'reply')
                    reply.goto(topic_url)
                    expect(reply.locator('[component="post/content"]').last).to_contain_text('预备会员的演示回复')
                    capture(reply, 'forum-topic')
                    checks.append('preparatory member replies through the real composer')
                    for role in ('member', 'officer'):
                        page = pages[role]
                        for path, method, body in (
                            ('/api/v3/topics', 'POST', {'cid': fixture['mailboxCid'], 'title': '不能发布', 'content': '禁止非机器人写入'}),
                            (f"/api/v3/topics/{fixture['mailboxTid']}", 'POST', {'content': '禁止非机器人回复'}),
                            (f"/api/v3/posts/{fixture['mailboxPid']}/vote", 'PUT', {'delta': 1}),
                        ):
                            result = api(page, path, method, body)
                            assert result['status'] == 403, (role, path, result)
                        checks.append(f'{role}: real mailbox create reply and vote endpoints are read-only')
                    member.goto(FORUM + f"/topic/{fixture['mailboxTid']}")
                    capture(member, 'forum-mailbox')
                finally:
                    for ctx in contexts.values():
                        ctx.close()
                    browser.close()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        User.objects.filter(pk__in=[u.pk for u in users.values() if u]).delete()
        (OUT / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, errors
    print(f'PASS: {len(checks)} real forum checks; production untouched; no IMAP transport claim')


if __name__ == '__main__':
    run()
