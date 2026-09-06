"""Isolated browser walkthrough. Never creates or edits production records."""
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'scripts')]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.work_audit'
os.environ['HEUESTA_WORK_AUDIT'] = '1'
os.environ['BILIBILI_API_ENABLED'] = '0'
from shoot import DevServer, do_login, port_open, settle

BASE = 'http://127.0.0.1:8821'
OUT = ROOT / '.shots/achievements'
PASSWORD = 'Local-Achievement-Audit-Only!'


def walkthrough(owner, member, claimant, staff):
    from playwright.sync_api import sync_playwright, expect
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        author = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        do_login(author, BASE, owner.username + ':' + PASSWORD)
        page = author.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE + '/works/mine/')
        page.get_by_role('button', name='新建作品').click()
        work_edit = page.url
        page.locator('[name=name]').fill('手册演示 · 共享信号源')
        page.locator('[name=year]').select_option('2026')
        page.locator('[name=department]').select_option('hardware')
        page.locator('[name=credit]').fill('虚构团队 · 成果体系验收')
        page.locator('[name=summary]').fill('本地隔离环境的演示作品，验证作品、团队与荣誉的关联。')
        page.locator('.ac-person-wrap').nth(0).locator('summary').click()
        page.locator('[name=people-0-name]').fill('演示设计者')
        page.locator('[name=people-0-role]').fill('电路设计')
        page.locator('[name=people-0-username]').fill(member.username)
        expect(page.locator('datalist option').first).to_have_attribute('value', member.username)
        page.get_by_role('button', name='添加参与者').click()
        expect(page.locator('[name=people-2-name]')).to_be_focused()
        # Leave the extra row empty; optional rows must not block submission.
        page.get_by_role('button', name='保存并预览').click()
        expect(page.locator('[name=consent]')).to_be_visible()
        page.locator('[name=consent]').check()
        page.get_by_role('button', name='确认发布作品', exact=True).click()
        work_public = page.url
        work_id = work_public.rstrip('/').split('/')[-1]
        expect(page.get_by_text('演示设计者', exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / 'work-with-contributors.png'), full_page=True)
        results.append('work: add registered participant, autocomplete, preview, publish')

        other = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        do_login(other, BASE, member.username + ':' + PASSWORD)
        member_page = other.new_page()
        member_page.goto(BASE + '/achievements/')
        member_page.get_by_role('button', name='这是我，确认关联').click()
        expect(member_page.get_by_role('heading', name='手册演示 · 共享信号源', exact=True)).to_be_visible()
        results.append('registered member confirms their own invitation')

        page.goto(BASE + '/achievements/honors/')
        page.get_by_role('button', name='录入荣誉').click()
        honor_edit = page.url
        page.locator('[name=title]').fill('手册演示 · 系统设计竞赛一等奖')
        page.locator('[name=contest]').fill('虚构赛事 · 不是真实获奖')
        page.locator('[name=year]').select_option('2026')
        page.locator('[name=level]').select_option('30')
        page.locator('[name=awardee]').fill('虚构团队 · 成果体系验收')
        page.locator('[name=project]').select_option(work_id)
        page.locator('[name=note]').fill('本地隔离测试，统一记录一项奖，不按人数重复计数。')
        page.locator('.ac-person-wrap').nth(0).locator('summary').click()
        page.locator('[name=people-0-name]').fill('演示设计者')
        page.locator('[name=people-0-username]').fill(member.username)
        page.locator('[name=people-0-role]').fill('电路设计')
        page.locator('.ac-person-wrap').nth(1).locator('summary').click()
        page.locator('[name=people-1-name]').fill('稍后认领的成员')
        page.locator('[name=people-1-role]').fill('软件开发')
        page.locator('[name=people-1-cohort]').select_option('2024')
        page.locator('[name=upload]').set_input_files(str(OUT / 'sample-certificate.png'))
        page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(page.get_by_text('荣誉草稿已保存，公开版本未改变。')).to_be_visible()
        cert_url = page.locator('.mw-asset-grid img').get_attribute('src')
        visitor = browser.new_context()
        assert visitor.request.get(BASE + cert_url).status == 404
        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1000 if width > 768 else 844})
            settle(page, True, 100)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'honor editor overflow {width}'
            page.screenshot(path=str(OUT / f'honor-editor-{width}.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('.mw-fields').screenshot(path=str(OUT / 'honor-fields.png'))
        page.locator('.ac-person-wrap').first.screenshot(path=str(OUT / 'contributors.png'))
        page.get_by_role('button', name='保存并预览').click()
        expect(page.locator('[name=consent]')).to_be_visible()
        page.screenshot(path=str(OUT / 'honor-preview.png'), full_page=True)
        page.locator('form').filter(has=page.locator('[name=consent]')).screenshot(path=str(OUT / 'honor-consent.png'))
        page.locator('[name=consent]').check()
        page.get_by_role('button', name='确认发布荣誉', exact=True).click()
        assert '/honors/' in page.url
        assert visitor.request.get(BASE + cert_url).status == 200
        page.screenshot(path=str(OUT / 'honor-wall.png'), full_page=True)
        results.append('honor: optional unregistered participant, protected certificate, linked work, own publication')
        page.goto(work_public)
        expect(page.get_by_role('link', name='2026 · 手册演示 · 系统设计竞赛一等奖')).to_be_visible()

        newcomer = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        do_login(newcomer, BASE, claimant.username + ':' + PASSWORD)
        claim_page = newcomer.new_page()
        claim_page.goto(BASE + '/achievements/catalog/?q=系统设计竞赛')
        claim_page.get_by_role('link', name='查看与认领').click()
        claim_page.locator('[name=contributor]').select_option(label='稍后认领的成员 · 2024 · 软件开发')
        claim_page.locator('[name=public_name]').fill('稍后认领的成员')
        claim_page.locator('[name=role]').fill('软件开发')
        claim_page.locator('[name=evidence]').fill('参与软件开发与联调，可向同队设计者核验；仅用于本地测试。')
        claim_page.locator('[name=consent]').check()
        claim_page.set_viewport_size({'width': 390, 'height': 1000})
        claim_page.locator('form').filter(has=claim_page.locator('[name=evidence]')).evaluate("el => el.scrollIntoView({block: 'end'})")
        claim_page.locator('form').filter(has=claim_page.locator('[name=evidence]')).screenshot(path=str(OUT / 'claim-form.png'))
        claim_page.screenshot(path=str(OUT / 'claim-mobile.png'), full_page=True)
        claim_page.get_by_role('button', name='提交核验申请').click()
        expect(claim_page.get_by_text('待核验', exact=True)).to_be_visible()
        staff_context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        do_login(staff_context, BASE, staff.username + ':' + PASSWORD)
        staff_page = staff_context.new_page()
        staff_page.goto(BASE + '/achievements/review/')
        staff_page.locator('[name=reason]').fill('已向团队核验，署名与分工对应。')
        staff_page.screenshot(path=str(OUT / 'claim-review.png'), full_page=True)
        staff_page.get_by_role('button', name='核验通过并关联').click()
        claim_page.reload()
        expect(claim_page.get_by_text('已关联', exact=True)).to_be_visible()
        for width in (1440, 768, 390, 320):
            claim_page.set_viewport_size({'width': width, 'height': 1000 if width > 768 else 844})
            settle(claim_page, True, 80)
            assert not claim_page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'hub overflow {width}'
            claim_page.screenshot(path=str(OUT / f'hub-{width}.png'), full_page=True)
        results.append('unlinked name: member claim, officer verification, status and association update')

        staff_page.goto(BASE + '/achievements/honors/manage/')
        staff_page.locator('[name=importance]').fill('80')
        staff_page.locator('[name=is_featured]').check()
        staff_page.get_by_role('button', name='保存排序').click()
        staff_page.locator('form').filter(has=staff_page.locator('[name=importance]')).screenshot(path=str(OUT / 'honor-ranking.png'))
        assert '手册演示 · 系统设计竞赛一等奖' in visitor.request.get(BASE + '/').text()
        results.append('officer ranking and homepage selection do not alter content')
        page.goto(honor_edit)
        page.locator('details').last.locator('summary').click()
        page.locator('[name=confirm]').check()
        page.get_by_role('button', name='撤回荣誉', exact=True).click()
        assert visitor.request.get(BASE + cert_url).status == 404
        assert '手册演示 · 系统设计竞赛一等奖' not in visitor.request.get(BASE + '/').text()
        assert '手册演示 · 系统设计竞赛一等奖' not in visitor.request.get(work_public).text()
        results.append('withdrawal revokes certificate and removes homepage/work cross-links')
        assert not errors, errors
        browser.close()
    return results


def main():
    if port_open(8821):
        raise SystemExit('Refusing to reuse an unknown server on 8821.')
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from PIL import Image, ImageDraw
    from news.models import Honor
    from projects.models import Project, WorkImage
    from achievements.models import Certificate
    assert Path(settings.DATABASES['default']['NAME']).resolve() == ROOT / '.shots/member-works-audit.sqlite3'
    call_command('migrate', interactive=False, verbosity=0)
    OUT.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (1000, 700), '#f2ece0')
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 970, 670), outline='#917147', width=4)
    draw.text((90, 130), 'LOCAL TEST CERTIFICATE / NOT A REAL AWARD', fill='#153743')
    image.save(OUT / 'sample-certificate.png')
    User = get_user_model()
    prefix = 'audit-ledger-' + uuid.uuid4().hex[:8]
    users = []
    try:
        for suffix, level in (('owner', 3), ('member', 3), ('claimant', 1), ('staff', 4)):
            users.append(User.objects.create_user(username=prefix + '-' + suffix, password=PASSWORD, member_level=level, is_active=True))
        with DevServer(8821):
            results = walkthrough(*users)
        (OUT / 'results.json').write_text(json.dumps({'checks': results, 'environment': 'isolated-local-only'}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        ids = [u.pk for u in users]
        files = [(im.image.storage, im.image.name) for im in Certificate.objects.filter(draft__owner_id__in=ids)]
        files += [(im.image.storage, im.image.name) for im in WorkImage.objects.filter(work__owner_id__in=ids)]
        Honor.objects.filter(member_draft__owner_id__in=ids).delete()
        Project.objects.filter(created_by_id__in=ids).delete()
        User.objects.filter(pk__in=ids).delete()
        for storage, name in files:
            storage.delete(name)


if __name__ == '__main__':
    main()
