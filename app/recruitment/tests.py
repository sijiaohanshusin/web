from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import roles

from .models import Application, Campaign

User = get_user_model()


def make_campaign(**kw):
    now = timezone.now()
    defaults = {
        "name": "2026 秋季招新",
        "intro": "欢迎加入！",
        "opens_at": now - timedelta(days=1),
        "closes_at": now + timedelta(days=7),
        "is_active": True,
    }
    defaults.update(kw)
    return Campaign.objects.create(**defaults)


def make_user(name="stu", level=roles.LEVEL_APPLICANT):
    u = User.objects.create_user(username=name, password="Str0ngPass!2025", is_active=True)
    u.set_level(level)
    return u


class CampaignModelTests(TestCase):
    def test_is_open_window(self):
        now = timezone.now()
        self.assertTrue(make_campaign().is_open)
        self.assertFalse(make_campaign(opens_at=now + timedelta(days=1)).is_open)
        self.assertFalse(make_campaign(closes_at=now - timedelta(days=1)).is_open)
        self.assertFalse(make_campaign(is_active=False).is_open)

    def test_open_ended_campaign(self):
        self.assertTrue(make_campaign(closes_at=None).is_open)


class ApplyFlowTests(TestCase):
    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = make_campaign()
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def test_index_shows_form_for_applicant(self):
        resp = self.client.get(reverse("recruitment:index"))
        self.assertContains(resp, "报名表")
        self.assertIn("no-cache", resp.headers["Cache-Control"])

    def test_apply_creates_application(self):
        resp = self.client.post(reverse("recruitment:apply"), {
            "department": "hardware",
            "skills": "会一点 C",
            "self_intro": "我是新生，非常想加入硬件部学习焊接。",
        })
        self.assertEqual(resp.status_code, 302)
        app = Application.objects.get(user=self.user, campaign=self.campaign)
        self.assertEqual(app.status, Application.Status.SUBMITTED)
        self.assertEqual(app.department, "hardware")

    def test_short_intro_rejected(self):
        resp = self.client.post(reverse("recruitment:apply"), {
            "department": "software", "skills": "", "self_intro": "太短",
        })
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        self.assertContains(resp, "自我介绍太短")

    def test_duplicate_apply_blocked(self):
        Application.objects.create(campaign=self.campaign, user=self.user, self_intro="第一次报名的自我介绍内容")
        self.client.post(reverse("recruitment:apply"), {
            "department": "hardware", "skills": "", "self_intro": "重复报名应当被拦截掉的内容",
        })
        self.assertEqual(Application.objects.filter(user=self.user).count(), 1)

    def test_pending_user_promoted_to_applicant_on_apply(self):
        pending = User.objects.create_user(username="p0", password="Str0ngPass!2025", is_active=True)
        pending.set_level(roles.LEVEL_PENDING)
        self.client.login(username="p0", password="Str0ngPass!2025")
        self.client.post(reverse("recruitment:apply"), {
            "department": "undecided", "skills": "", "self_intro": "零基础但很想学，请给我机会。",
        })
        pending.refresh_from_db()
        self.assertEqual(pending.member_level, roles.LEVEL_APPLICANT)

    def test_formal_member_cannot_apply(self):
        formal = make_user("formal", roles.LEVEL_FORMAL)
        self.client.login(username="formal", password="Str0ngPass!2025")
        resp = self.client.post(reverse("recruitment:apply"), {
            "department": "hardware", "skills": "", "self_intro": "我已经是科协会员了还来报名。",
        }, follow=True)
        self.assertFalse(Application.objects.filter(user=formal).exists())
        self.assertContains(resp, "已经是科协会员")


class RecruitDashboardTests(TestCase):
    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = make_campaign()
        self.officer = make_user("off", roles.LEVEL_OFFICER)
        self.applicant = make_user("newbie", roles.LEVEL_APPLICANT)
        self.app = Application.objects.create(
            campaign=self.campaign, user=self.applicant, self_intro="想加入的自我介绍内容足够长。",
        )
        self.client.login(username="off", password="Str0ngPass!2025")

    def test_member_cannot_access(self):
        make_user("plain")
        self.client.login(username="plain", password="Str0ngPass!2025")
        resp = self.client.get(reverse("dashboard:recruitment"))
        self.assertEqual(resp.status_code, 403)

    def test_first_pass_promotes_to_preparatory(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "first_pass", "ids": [self.app.pk],
            "note": "表现不错",
        })
        self.app.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.FIRST_PASS)
        self.assertEqual(self.app.interview_note, "表现不错")
        self.assertEqual(self.applicant.member_level, roles.LEVEL_PREPARATORY)

    def test_second_pass_promotes_to_formal(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "second_pass", "ids": [self.app.pk],
        })
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.member_level, roles.LEVEL_FORMAL)

    def test_reject_notifies_and_no_promotion(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "reject", "ids": [self.app.pk],
        })
        self.app.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.REJECTED)
        self.assertEqual(self.applicant.member_level, roles.LEVEL_APPLICANT)
        self.assertEqual(self.applicant.notifications.filter(title__contains="招新结果").count(), 1)

    def test_csv_export(self):
        resp = self.client.get(reverse("dashboard:recruitment"), {"campaign": self.campaign.pk, "export": "csv"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn("newbie", resp.content.decode("utf-8-sig"))

    def test_campaign_create(self):
        start = timezone.now()
        resp = self.client.post(reverse("dashboard:campaign_create"), {
            "name": "2027 春季招新",
            "intro": "## 招新\n\n春季补录",
            "opens_at": start.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (start + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Campaign.objects.filter(name="2027 春季招新").exists())


class CampaignCurrentTests(TestCase):
    """Campaign.current() —— 对外展示用的「当前批次」。

    这个答案有三个消费者：报名页、导航条的招新入口、首页 CTA 的倒计时。逻辑放在
    模型上就是为了让三处永远一致，否则迟早出现「导航说在招新、首页说已截止」。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.now = timezone.now()

    def test_prefers_an_open_campaign_over_a_newer_closed_one(self):
        """开放中的优先，即使有更新的批次已经截止。"""
        open_one = Campaign.objects.create(
            name="进行中", is_active=True,
            opens_at=self.now - timedelta(days=10),
            closes_at=self.now + timedelta(days=5),
        )
        Campaign.objects.create(
            name="更新但已截止", is_active=True,
            opens_at=self.now - timedelta(days=1),
            closes_at=self.now - timedelta(hours=1),
        )
        self.assertEqual(Campaign.current(), open_one)

    def test_falls_back_to_the_latest_active_when_none_is_open(self):
        """全都不在窗口内时给最近的那个 —— 报名页要有东西可展示。"""
        Campaign.objects.create(
            name="旧的", is_active=True,
            opens_at=self.now - timedelta(days=100),
            closes_at=self.now - timedelta(days=90),
        )
        newest = Campaign.objects.create(
            name="最近的", is_active=True,
            opens_at=self.now - timedelta(days=2),
            closes_at=self.now - timedelta(days=1),
        )
        self.assertEqual(Campaign.current(), newest)

    def test_ignores_disabled_campaigns(self):
        Campaign.objects.create(
            name="停用的", is_active=False,
            opens_at=self.now - timedelta(days=1),
            closes_at=self.now + timedelta(days=5),
        )
        self.assertIsNone(Campaign.current())

    def test_none_when_there_are_no_campaigns_at_all(self):
        Campaign.objects.all().delete()
        self.assertIsNone(Campaign.current())


class ApplicationProgressTests(TestCase):
    """报名进度的模型侧语义。

    页面的时间线直接读这两个属性，所以「走到第几步」的判断只有一处实现。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = Campaign.objects.create(
            name="批次", is_active=True,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=5),
        )
        self.user = User.objects.create_user(username="applicant2", password="x")
        self.user.set_level(roles.LEVEL_APPLICANT)

    def _app(self, status):
        return Application.objects.create(
            campaign=self.campaign, user=self.user,
            self_intro="够长的自我介绍内容。", status=status,
        )

    def test_reached_index_follows_the_three_steps(self):
        cases = {
            Application.Status.SUBMITTED: 0,
            Application.Status.FIRST_PASS: 1,
            Application.Status.SECOND_PASS: 2,
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                app = self._app(status)
                self.assertEqual(app.reached_index, expected)
                app.delete()

    def test_rejected_is_a_terminal_state_not_a_fourth_step(self):
        """未录取不进时间线：它是任何一步都可能走到的终止态，不是「最后一个成就」。"""
        app = self._app(Application.Status.REJECTED)
        self.assertTrue(app.is_rejected)
        # 只能确定「报名」这一步成立 —— 数据库不保留「之前通过到哪一面」
        self.assertEqual(app.reached_index, 0)
        self.assertEqual(len(Application.PROGRESS_STEPS), 3)
        keys = [k for k, _, _ in Application.PROGRESS_STEPS]
        self.assertNotIn(Application.Status.REJECTED, keys)


class RecruitmentPageStateTests(TestCase):
    """招新落地页的状态分支与实时数据。

    渲染层面的完整验证（六种状态真的打开页面看）在 scripts/check_recruitment.py。
    这里守服务端算出来的东西：四态标志位、统计口径、以及「方向」必须是单选卡片。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.url = reverse("recruitment:index")
        self.campaign = Campaign.objects.create(
            name="2026 测试招新", is_active=True,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=7),
        )

    def _login(self, level):
        user = User.objects.create_user(username=f"u{level}", password="x")
        user.set_level(level)
        self.client.login(username=f"u{level}", password="x")
        return user

    def test_anonymous_gets_no_form(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context["can_apply"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_applicant_can_apply(self):
        self._login(roles.LEVEL_APPLICANT)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context["can_apply"])
        self.assertContains(resp, 'id="rec-form"')
        # 三段 fieldset —— 分步是前端的事，但段落划分在模板里。
        # 属性名是 form-enhance.js 的通用契约（注册表单也用同一套）。
        body = resp.content.decode()
        self.assertEqual(body.count("data-step>"), 3)
        self.assertIn("data-stepped-form", body)

    def test_formal_member_gets_no_form(self):
        self._login(roles.LEVEL_FORMAL)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context["already_member"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_existing_application_replaces_the_form_with_a_track(self):
        user = self._login(roles.LEVEL_APPLICANT)
        Application.objects.create(
            campaign=self.campaign, user=user, self_intro="够长的自我介绍内容。",
        )
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'id="rec-form"')
        self.assertContains(resp, "rec-track")

    def test_closed_campaign_gets_no_form(self):
        self._login(roles.LEVEL_APPLICANT)
        self.campaign.closes_at = timezone.now() - timedelta(hours=1)
        self.campaign.save(update_fields=["closes_at"])
        resp = self.client.get(self.url)
        self.assertFalse(resp.context["can_apply"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_no_active_campaign_at_all(self):
        Campaign.objects.update(is_active=False)
        resp = self.client.get(self.url)
        self.assertIsNone(resp.context["campaign"])
        self.assertContains(resp, "招新通道")

    def test_stats_count_by_department_in_one_query(self):
        u1 = User.objects.create_user(username="a1", password="x")
        u2 = User.objects.create_user(username="a2", password="x")
        for user, dept in ((u1, Application.Department.HARDWARE),
                           (u2, Application.Department.HARDWARE)):
            Application.objects.create(
                campaign=self.campaign, user=user, department=dept,
                self_intro="够长的自我介绍内容。",
            )
        resp = self.client.get(self.url)
        stats = resp.context["stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(dict(stats["breakdown"])["硬件部"], 2)
        self.assertEqual(dict(stats["breakdown"])["软件部"], 0)

    def test_department_is_radio_cards_not_a_dropdown(self):
        """三个选项用卡片：移动端不弹系统选择器，也更适合「选方向」这种决定。"""
        self._login(roles.LEVEL_APPLICANT)
        body = self.client.get(self.url).content.decode()
        self.assertIn('type="radio"', body)
        self.assertIn("rec-choice-item", body)
        self.assertNotIn('<select name="department"', body)
