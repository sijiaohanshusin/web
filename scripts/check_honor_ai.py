"""Local browser acceptance with a mocked provider, never calls Aliyun or production."""
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'scripts')]
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.work_audit', HEUESTA_WORK_AUDIT='1',
    HONOR_AI_ENABLED='1', DASHSCOPE_API_KEY='local-browser-test-not-a-key', DASHSCOPE_WORKSPACE_ID='local-test',
    HONOR_AI_FREE_TIER_CONFIRMED='1', HONOR_AI_FREE_TIER_EXPIRES='2099-01-01T00:00:00+00:00')
from shoot import DevServer, do_login, port_open

BASE = 'http://127.0.0.1:8831'
OUT = ROOT / '.shots/honor-ai'
PASSWORD = 'Local-Only-Honor-Demo!'
SAMPLE = {'title':'虚构赛事 · 智能系统设计一等奖','contest':'虚构赛事 · 硬件赛道','year':'2026',
    'level':'省级','level_evidence':'省赛一等奖','awardee':'演示联合队',
    'work_name':'桌面信号源','teachers':'演示导师',
    'contributors':[{'name':'演示甲','role':'队员'}, {'name':'演示乙','role':'队员'}]}


def db(call, *args):
    # Playwright's synchronous API still runs an event loop on the caller thread.
    def invoke():
        from django.db import connections
        try:
            return call(*args)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as worker:
        return worker.submit(invoke).result()


def run(owner, draft):
    from achievements import recognition
    from playwright.sync_api import sync_playwright, expect
    results = []
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        context=browser.new_context(viewport={'width':1440,'height':1000}, reduced_motion='reduce')
        do_login(context,BASE,owner.username+':'+PASSWORD)
        page=context.new_page();errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.goto(BASE+f'/achievements/honors/{draft.pk}/')
        expect(page.locator('[name=year]')).to_have_value('')
        page.locator('[name=title]').fill('我手动填写的标题')
        page.locator('#hr-file').set_input_files(str(OUT/'test-certificate.png'))
        page.locator('#hr-consent').check()
        with page.expect_response('**/recognize/') as job:
            page.locator('#hr-start').click()
        assert job.value.status == 202
        page.locator('[name=contest]').fill('识别期间的新输入')
        with patch.object(recognition,'call_model',return_value=(SAMPLE,{'total_tokens':500})):
            assert db(recognition.process_one)
        expect(page.locator('#hr-status')).to_contain_text('识别完成',timeout=20000)
        expect(page.locator('[name=title]')).to_have_value('我手动填写的标题')
        expect(page.locator('[name=contest]')).to_have_value('识别期间的新输入')
        expect(page.locator('[name=year]')).to_have_value('2026')
        expect(page.locator('[name=level]')).to_have_value('20')
        expect(page.locator('[name=certificate]')).to_have_value('')
        expect(page.locator('[name=people-0-name]')).to_have_value('演示甲')
        expect(page.locator('[name=people-0-username]')).to_have_value('')
        db(draft.refresh_from_db);assert draft.draft == {} and draft.published is None
        image=db(draft.images.get)
        visitor=browser.new_context()
        assert visitor.request.get(BASE+image.public_url).status == 404
        page.locator('#honor-recognition').screenshot(path=str(OUT/'manual-honor-ai-result.png'))
        page.set_viewport_size({'width':768,'height':1024})
        page.locator('.hr-controls').screenshot(path=str(OUT/'manual-honor-ai-source.png'))
        page.locator('.hr-review').screenshot(path=str(OUT/'manual-honor-ai-review.png'))
        for width in (1440,768,390,320):
            page.set_viewport_size({'width':width,'height':1000 if width>768 else 844})
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
            page.screenshot(path=str(OUT/f'editor-{width}.png'),full_page=True)
            page.locator('#honor-recognition').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/f'editor-viewport-{width}.png'))
        page.locator('[name=awardee]').fill('后来修正的团队名')
        page.locator('#hr-undo').click()
        expect(page.locator('[name=awardee]')).to_have_value('后来修正的团队名')
        expect(page.locator('[name=year]')).to_have_value('')
        expect(page.locator('[name=people-0-name]')).to_have_value('')
        page.route('**/recognize/', lambda route: route.fulfill(status=503, content_type='application/json',
            body=json.dumps({'error':'识别服务暂时不可用，请继续手动填写。'})))
        page.locator('#hr-start').click()
        expect(page.locator('#hr-status')).to_contain_text('暂时不可用')
        expect(page.locator('[name=awardee]')).to_have_value('后来修正的团队名')
        expect(page.locator('#hr-image')).to_have_value(str(image.pk))
        expect(page.locator('#hr-start')).to_be_enabled()
        page.unroute('**/recognize/')
        with page.expect_response('**/recognize/'):
            page.locator('#hr-start').click()
        expect(page.locator('#hr-status')).to_contain_text('识别完成')
        page.locator('[name=title]').fill(SAMPLE['title'])
        page.locator('[name=contest]').fill(SAMPLE['contest'])
        page.locator('[name=certificate]').select_option(str(image.pk))
        page.get_by_role('button',name='保存并预览').click()
        page.locator('[name=consent]').check()
        page.get_by_role('button',name='确认发布荣誉',exact=True).click()
        assert visitor.request.get(BASE+image.public_url).status==200
        db(draft.refresh_from_db)
        from achievements import honor_services
        db(honor_services.withdraw,owner,draft.pk,draft.version)
        assert visitor.request.get(BASE+image.public_url).status==404
        results.append('real upload/job/poll + mocked model, input race, differences, undo, service failure recovery, publish/withdraw privacy')

        for width in (1440,768,390,320):
            page.set_viewport_size({'width':width,'height':900})
            page.goto(BASE+'/recruitment/')
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
            page.screenshot(path=str(OUT/f'recruit-{width}.png'))
        context.clear_cookies()
        page.emulate_media(reduced_motion='no-preference')
        page.goto(BASE+'/recruitment/')
        page.wait_for_timeout(2000)
        page.locator('[data-recruit-robot]').focus()
        page.keyboard.press('Enter')
        expect(page.locator('[data-recruit-robot]')).to_have_class('rec-robot is-playing')
        page.emulate_media(reduced_motion='reduce')
        expect(page.locator('[data-recruit-robot]')).not_to_have_class('rec-robot is-playing')
        for anchor in ('hardware','software','training'):
            page.goto(BASE+'/recruit/#'+anchor);page.wait_for_timeout(2800)
            box=page.locator('#'+anchor+' > h2').bounding_box()
            assert box['y']>=75 and box['y']<150,(anchor,box)
        nojs=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
        fallback=nojs.new_page();fallback.goto(BASE+'/')
        assert fallback.locator('.nf-dir-card').first.evaluate('(e)=>getComputedStyle(e).opacity')=='1'
        for anchor in ('hardware','software','training'):
            fallback.goto(BASE+'/recruit/#'+anchor)
            assert fallback.locator('#'+anchor+' > h2').is_visible()
        results.append('four widths, keyboard replay/reduced motion, fragment alignment, no-JS readable content')
        assert not errors,errors
        browser.close()
    return results


def main():
    if port_open(8831):raise SystemExit('Refusing an unknown existing server on 8831')
    OUT.mkdir(parents=True,exist_ok=True)
    import django
    django.setup()
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from achievements import honor_services
    from achievements.models import RecognitionGate
    from news.models import Honor
    from PIL import Image, ImageDraw
    call_command('migrate',interactive=False,verbosity=0)
    RecognitionGate.objects.update_or_create(pk=1,defaults={'counters':{},'busy_until':None,'lease':None,'blocked_for':''})
    img=Image.new('RGB',(1000,700),'#f4eedf');draw=ImageDraw.Draw(img)
    draw.rectangle((30,30,970,670),outline='#936d3c',width=4)
    draw.text((100,180),'FICTIONAL CERTIFICATE / LOCAL BROWSER TEST ONLY',fill='#24424a')
    img.save(OUT/'test-certificate.png')
    user=get_user_model().objects.create_user(username='ai-local-'+uuid.uuid4().hex[:8],password=PASSWORD,member_level=3,is_active=True)
    draft=honor_services.create(user)
    try:
        with DevServer(8831):results=run(user,draft)
        (OUT/'checks.json').write_text(json.dumps({'checks':results,'provider':'mock only','real_device_tested':False},indent=2),encoding='utf-8')
        print(json.dumps(results))
    finally:
        for image in draft.images.all():image.image.delete(save=False)
        Honor.objects.filter(member_draft=draft).delete()
        user.delete()


if __name__=='__main__':main()
