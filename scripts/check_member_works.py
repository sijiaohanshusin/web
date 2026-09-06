"""Local-only real-browser author publication and officer ranking walkthrough."""
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'scripts')]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.work_audit'
os.environ['HEUESTA_WORK_AUDIT'] = '1'
os.environ['BILIBILI_API_ENABLED'] = '0'
from shoot import DevServer, do_login, port_open, settle

PORT = 8818
BASE = f'http://127.0.0.1:{PORT}'
OUT = ROOT / '.shots/member-works'
PASSWORD = 'WorksLocal-Only-2026!'


def check(owner, officer):
    from playwright.sync_api import sync_playwright, expect
    results = []
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        author = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        do_login(author, BASE, owner.username + ':' + PASSWORD)
        page = author.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        page.goto(BASE + '/works/')
        page.get_by_role('link', name='我的作品 · 上传与发布').click()
        page.get_by_role('button', name='新建作品').click()
        edit_url = page.url
        for field, value in {'name': '口袋信号源 · 本地演示', 'credit': '演示成员 · 电路与固件',
                             'highlight': '让测量工具走出实验室', 'tags': 'STM32, 开源硬件',
                             'summary': '这是一件虚构的本地测试作品。\n从原理图、焊接到固件，记录每一步验证。',
                             'external_url': 'https://example.com/demo'}.items():
            page.locator(f'[name={field}]').fill(value)
        page.locator('[name=department]').select_option('hardware')
        page.locator('[name=year]').select_option('2026')
        page.locator('[name=upload]').set_input_files(str(ROOT / 'app/showcase/demo_assets/signal.png'))
        page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(page.locator('.mw-state')).to_contain_text('v1')
        asset = page.locator('.mw-asset-grid img').first.get_attribute('src')
        visitor = browser.new_context()
        assert visitor.request.get(BASE + asset).status == 404
        assert visitor.request.get(edit_url).status == 200  # Redirects to login, never a draft.
        assert '/accounts/login/' in visitor.request.get(edit_url).url
        results.append('uploaded image and draft are private')

        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1000 if width > 768 else 844})
            settle(page, True, 100)
            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow, f'editor overflow at {width}'
            page.screenshot(path=str(OUT / f'editor-{width}.png'), full_page=True)
            if width == 1440:
                from PIL import Image
                bounds = page.locator('.mw-form').evaluate('el => { const r=el.getBoundingClientRect(); return {x:r.x+scrollX,y:r.y+scrollY,w:r.width,h:r.height}; }')
                # Crop the real full-page screenshot, avoiding fixed-nav overlays on element screenshots.
                with Image.open(OUT / 'editor-1440.png') as capture:
                    x, y, w, h = (bounds[key] for key in ('x', 'y', 'w', 'h'))
                    capture.crop((int(x), int(y+h-290), int(x+w), int(y+h))).save(OUT / 'editor-form.png')
        results.append('editor: five widths, no horizontal overflow')
        page.set_viewport_size({'width': 1440, 'height': 1000})
        stale = author.new_page()
        stale.goto(edit_url)
        page.get_by_role('button', name='保存并预览').click()
        settle(page, True, 100)
        page.screenshot(path=str(OUT / 'preview-1440.png'), full_page=True)
        page.locator('.mw-confirm').screenshot(path=str(OUT / 'publish-confirm.png'))
        page.locator('[name=consent]').check()
        page.get_by_role('button', name='确认发布作品', exact=True).click()
        public_url = page.url
        expect(page.locator('h1')).to_contain_text('口袋信号源')
        assert visitor.request.get(public_url).status == 200
        assert visitor.request.get(BASE + asset).status == 200
        wall = visitor.new_page()
        wall.goto(BASE + '/works/')
        public_path = public_url.removeprefix(BASE)
        expect(wall.locator(f'.wk-grid a[href="{public_path}"]')).to_have_count(1)
        settle(wall, True, 100)
        wall.screenshot(path=str(OUT / 'wall-published-1440.png'), full_page=True)
        results.append('owner previews and publishes directly without officer approval')
        stale.locator('[name=name]').fill('过时标签页不得覆盖')
        with stale.expect_response(lambda response: response.url == edit_url and response.request.method == 'POST') as reply:
            stale.get_by_role('button', name='保存草稿', exact=True).click()
        assert reply.value.status == 409
        expect(stale.locator('[name=name]')).to_have_value('过时标签页不得覆盖')
        stale.close()
        results.append('stale tab receives 409 and retains input')

        for width in (1440, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1000 if width > 768 else 844})
            settle(page, True, 100)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'detail overflow at {width}'
            page.screenshot(path=str(OUT / f'public-{width}.png'), full_page=True)
        page.goto(edit_url)
        page.locator('[name=name]').fill('未发布的新草稿')
        page.get_by_role('button', name='保存草稿', exact=True).click()
        live = visitor.new_page()
        live.goto(public_url)
        expect(live.locator('h1')).to_contain_text('口袋信号源')
        results.append('saving new draft leaves public snapshot intact')
        staff = browser.new_context(viewport={'width': 1440, 'height': 1000})
        do_login(staff, BASE, officer.username + ':' + PASSWORD)
        rank = staff.new_page()
        rank.goto(BASE + '/works/manage/')
        rank.locator('[name=importance]').first.fill('75')
        rank.locator('[name=is_featured]').first.check()
        rank.get_by_role('button', name='保存排序').first.click()
        expect(rank.locator('[name=importance]').first).to_have_value('75')
        assert staff.request.get(edit_url).status == 404
        settle(rank, False, 600)
        rank.screenshot(path=str(OUT / 'ranking-1440.png'), full_page=True)
        results.append('officer ranks published work but cannot access private draft')
        page.goto(edit_url)
        page.get_by_text('撤回与删除', exact=True).click()
        page.locator('.mw-danger [name=confirm]').check()
        page.get_by_role('button', name='撤回作品', exact=True).click()
        assert visitor.request.get(public_url).status == 404
        assert visitor.request.get(BASE + asset).status == 404
        wall.reload()
        expect(wall.locator(f'.wk-grid a[href="{public_path}"]')).to_have_count(0)
        results.append('member uploads from wall; anonymous visitors see publication and not withdrawal')
        results.append('withdrawal closes public page and protected image')
        # Exercise progressively enhanced forms: publication remains usable without JS.
        nojs = browser.new_context(java_script_enabled=False)
        do_login(nojs, BASE, owner.username + ':' + PASSWORD)
        plain = nojs.new_page()
        plain.goto(edit_url)
        plain.locator('[name=name]').fill('无脚本仍可保存')
        plain.get_by_role('button', name='保存并预览').click()
        expect(plain.locator('h1').last).to_have_text('无脚本仍可保存')
        results.append('no-JavaScript editing, saving and preview work')
        assert not errors, errors
        browser.close()
    (OUT / 'checks.json').write_text(json.dumps({'local_only': True, 'passed': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from accounts.models import User
    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots/member-works-audit.sqlite3'
    assert not port_open(PORT), 'Do not reuse an unknown running server for write tests'
    OUT.mkdir(parents=True, exist_ok=True)
    call_command('migrate', verbosity=0)
    suffix = uuid.uuid4().hex[:8]
    users = [User.objects.create_user(username=f'local-works-{role}-{suffix}', password=PASSWORD,
             real_name='本地演示成员' if level == 3 else '本地演示站务', member_level=level)
             for role, level in (('member', 3), ('officer', 4))]
    try:
        with DevServer(PORT):
            if '--serve' in sys.argv:
                print(f'LOCAL ONLY {BASE}/works/mine/ username={users[0].username} password={PASSWORD}', flush=True)
                while True:
                    time.sleep(1)
            else:
                check(*users)
    finally:
        for user in users:
            user.delete()


if __name__ == '__main__':
    main()
