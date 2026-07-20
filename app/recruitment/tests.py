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
        self.campaign = make_campaign()
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def test_index_shows_form_for_applicant(self):
        resp = self.client.get(reverse("recruitment:index"))
        self.assertContains(resp, "报名表")

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
            "department": "hardware", "skills": "", "self_intro": "我已经是正式会员了还来报名。",
        }, follow=True)
        self.assertFalse(Application.objects.filter(user=formal).exists())
        self.assertContains(resp, "已经是正式会员")


class RecruitDashboardTests(TestCase):
    def setUp(self):
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
