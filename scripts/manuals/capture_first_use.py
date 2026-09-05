"""Capture real first-use controls using disposable local data only."""
import json
import os
from pathlib import Path
import sys
from datetime import timedelta
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'scripts')]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_audit'
os.environ['HEUESTA_BROWSER_AUDIT'] = '1'
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
from shoot import DevServer, do_login, port_open
from playwright.sync_api import sync_playwright, expect


def shot(page, locator, name):
    page.evaluate('document.fonts.ready')
    locator.scroll_into_view_if_needed()
    locator.screenshot(path=str(ROOT / 'app/helpcenter/assets' / name), animations='disabled')
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.utils import timezone
    from accounts.models import User
    from core.models import Feedback
    from events.models import Event, EventSignup
    from recruitment.models import Campaign
    assert settings.DEBUG and settings.DATABASES['default']['NAME'] == ROOT / '.shots/roles.sqlite3'
    port = 8815
    assert not port_open(port), 'Refuse an unknown existing server'
    call_command('migrate', verbosity=0)
    prefix = 'first-use-' + uuid.uuid4().hex[:6]
    password = uuid.uuid4().hex + 'Local!'
    users, records, checks = [], [], []
    try:
        for name, level in [('招新演示',1),('会员演示',3),('站务演示',4)]:
            users.append(User.objects.create_user(username=prefix+str(level), real_name='手册'+name,
                password=password, member_level=level, grade='2026', specialty='software',
                college='信息与通信工程学院'))
        recruit, member, officer = users
        now = timezone.now()
        campaign = Campaign.objects.create(name='手册演示招新', opens_at=now-timedelta(minutes=1), intro='仅用于隔离环境操作演示。')
        records.append(campaign)
        event = Event.objects.create(title='手册演示 电子制作入门', description='仅用于隔离环境操作演示，不是正式活动。',
            start_at=now+timedelta(days=1), end_at=now+timedelta(days=1,hours=2),
            capacity=20, min_level=3, location='演示实验室', created_by=officer)
        records.append(event)
        feedback = Feedback.objects.create(user=member, page='/help/member/',
            content='手册演示：首次使用时希望找到如何报名活动的步骤。此记录只用于隔离验收。')
        records.append(feedback)
        with DevServer(port), sync_playwright() as pw:
            browser = pw.chromium.launch()
            base = f'http://127.0.0.1:{port}'
            contexts = []
            for user in users:
                ctx = browser.new_context(viewport={'width':390 if user == recruit else 1280,'height':920}, reduced_motion='reduce')
                ctx.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
                do_login(ctx,base,f'{user.username}:{password}')
                contexts.append(ctx)
            page = contexts[0].new_page()
            page.goto(base+'/recruitment/')
            form = page.locator('#rec-form')
            form.locator('[name=department]').first.check()
            form.locator('[data-step-next]').click()
            form.locator('[name=interests]').first.check()
            form.locator('[data-step-next]').click()
            form.locator('[name=skills]').fill('零基础，希望从焊接与编程练习开始。')
            form.locator('[data-step-next]').click()
            form.locator('[name=self_intro]').fill('希望和伙伴一起把想法做成作品，愿意参加每周练习。')
            shot(page, form.locator('[data-step]').nth(3), 'first-use-application-mobile.png')
            checks.append('mobile applicant reaches and fills introduction without submitting')

            member_page = contexts[1].new_page()
            member_page.goto(base+event.get_absolute_url())
            shot(member_page, member_page.locator('.event-info-panel'), 'first-use-event-info.png')
            member_page.get_by_role('button',name='立即报名',exact=True).click()
            expect(member_page.locator('body')).to_contain_text('已报名')
            assert EventSignup.objects.filter(event=event,user=member).count()==1
            shot(member_page, member_page.locator('.event-action-box'), 'first-use-event-signed.png')
            checks.append('member browser signup creates one record and shows cancellation')
            member_page.on('dialog', lambda dialog:dialog.accept())
            member_page.get_by_role('button',name='取消报名',exact=True).click()
            assert not EventSignup.objects.filter(event=event,user=member).exists()
            member_page.get_by_role('button',name='立即报名',exact=True).click()
            checks.append('member cancellation and re-registration retain one signup')

            staff = contexts[2].new_page()
            staff.goto(base+'/dashboard/events/?q='+event.title)
            row = staff.locator('tbody tr').filter(has_text=event.title)
            shot(staff,row,'first-use-event-management.png')
            row.get_by_role('button',name='开启签到',exact=True).click()
            event.refresh_from_db()
            assert event.checkin_open
            member_page.reload()
            member_page.locator('[name=code]').fill(event.checkin_code)
            member_page.locator('.event-checkin-form button').click()
            expect(member_page.locator('body')).to_contain_text('已签到')
            assert EventSignup.objects.get(event=event,user=member).checked_in
            checks.append('staff opens check-in and member submits the real local code')
            staff.reload()
            staff.get_by_role('button',name='关闭签到',exact=True).click()
            event.refresh_from_db()
            assert not event.checkin_open
            checks.append('staff closes check-in after member result verified')

            staff.goto(base+'/dashboard/feedbacks/')
            card = staff.locator('.fb-card').filter(has_text=feedback.content)
            shot(staff,card,'first-use-feedback-actions.png')
            card.locator('[name=note]').fill('已提供活动报名帮助入口，请按步骤尝试。')
            card.locator('.fb-resolve-form button').click()
            feedback.refresh_from_db()
            assert feedback.status == 'resolved'
            checks.append('staff resolves only the synthetic feedback with a visible note')
            staff.goto(base+'/dashboard/feedbacks/?tab=all')
            staff.locator('.fb-card').filter(has_text=feedback.content).get_by_role('button',name='重新打开',exact=True).click()
            feedback.refresh_from_db()
            assert feedback.status == 'pending'
            checks.append('resolved feedback can be reopened without losing its record')
            member_page.set_viewport_size({'width':390,'height':920})
            member_page.goto(base+'/accounts/profile/edit/')
            member_page.locator('[name=specialty]').select_option('custom')
            member_page.locator('[name=specialty_custom]').fill('交互设计与电子制作')
            a = member_page.locator('.form-group').filter(has=member_page.locator('[name=specialty]'))
            b = member_page.locator('.form-group').filter(has=member_page.locator('[name=specialty_custom]'))
            # The conditional field animates open; capture only after its full
            # input fits inside the measured group, not an intermediate height.
            member_page.wait_for_function('''() => {
                const input = document.querySelector('[name=specialty_custom]');
                const group = input.closest('.form-group');
                return group.getBoundingClientRect().bottom >= input.getBoundingClientRect().bottom;
            }''')
            a.evaluate("element => window.scrollTo({top: scrollY + element.getBoundingClientRect().top - 120, behavior: 'instant'})")
            first, second = a.bounding_box(), b.bounding_box()
            input_box = member_page.locator('[name=specialty_custom]').bounding_box()
            bottom = max(second['y'] + second['height'], input_box['y'] + input_box['height']) + 4
            assert first['y'] >= 0 and bottom <= 920
            member_page.screenshot(path=str(ROOT/'app/helpcenter/assets/first-use-profile-direction.png'),
                clip={'x':first['x'],'y':first['y'],'width':first['width'],
                      'height':bottom-first['y']},animations='disabled')
            member_page.locator('[data-profile-save]').click()
            member_page.wait_for_url('**/accounts/profile/')
            member.refresh_from_db()
            assert member.specialty_custom=='交互设计与电子制作'
            checks.append('mobile custom direction text is saved without publishing a showcase')
            for ctx in contexts:
                ctx.close()
            browser.close()
    finally:
        for record in reversed(records):
            record.delete()
        User.objects.filter(pk__in=[u.pk for u in users]).delete()
    (ROOT/'.shots/first-use').mkdir(parents=True,exist_ok=True)
    (ROOT/'.shots/first-use/browser-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'PASS {len(checks)} local first-use browser checks; disposable records removed')


if __name__=='__main__':
    run()
