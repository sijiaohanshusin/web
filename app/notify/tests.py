from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import roles
from accounts.models import Medal, UserMedal
from core.models import Feedback

from .models import Notification
from .services import notify_user, notify_users

User = get_user_model()


class NotifyServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="x", is_active=True)

    def test_notify_user_creates(self):
        n = notify_user(self.user, "标题", body="内容", url="/news/1/")
        self.assertIsNotNone(n)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertFalse(n.is_read)

    def test_notify_none_user_skipped(self):
        self.assertIsNone(notify_user(None, "标题"))

    def test_notify_users_bulk(self):
        u2 = User.objects.create_user(username="u2", password="x")
        count = notify_users([self.user, u2, None], "群发")
        self.assertEqual(count, 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_title_truncated(self):
        n = notify_user(self.user, "长" * 300)
        self.assertEqual(len(n.title), 120)


class NotifyViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="Str0ngPass!2025", is_active=True)
        self.client.login(username="u1", password="Str0ngPass!2025")

    def test_list_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("notify:list"))
        self.assertEqual(resp.status_code, 302)

    def test_list_renders_items(self):
        notify_user(self.user, "第一条通知", body="正文片段")
        resp = self.client.get(reverse("notify:list"))
        self.assertContains(resp, "第一条通知")
        self.assertContains(resp, "正文片段")
        resp = self.client.get(reverse("notify:list"), {"tab": "unread"})
        self.assertContains(resp, "第一条通知")

    def test_go_marks_read_and_redirects(self):
        n = notify_user(self.user, "看这里", url="/resources/")
        resp = self.client.get(reverse("notify:go", args=[n.pk]))
        self.assertRedirects(resp, "/resources/")
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_go_rejects_other_users_notification(self):
        other = User.objects.create_user(username="u2", password="x")
        n = notify_user(other, "别人的")
        resp = self.client.get(reverse("notify:go", args=[n.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_mark_all_read(self):
        notify_user(self.user, "一")
        notify_user(self.user, "二")
        self.client.post(reverse("notify:read_all"))
        self.assertEqual(self.user.notifications.filter(read_at__isnull=True).count(), 0)

    def test_latest_json(self):
        notify_user(self.user, "hello")
        resp = self.client.get(reverse("notify:latest_json"))
        data = resp.json()
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["items"][0]["title"], "hello")

    def test_unread_badge_in_nav(self):
        notify_user(self.user, "未读")
        resp = self.client.get(reverse("core:home"))
        self.assertContains(resp, "nav-bell-badge")


class NotifyIntegrationTests(TestCase):
    """业务事件应产生站内通知。"""

    def test_set_level_notifies(self):
        u = User.objects.create_user(username="lv", password="x")
        u.set_level(roles.LEVEL_FORMAL, note="二面通过")
        n = u.notifications.get()
        self.assertEqual(n.kind, Notification.Kind.LEVEL)
        self.assertIn("正式会员", n.title)
        self.assertIn("二面通过", n.body)

    def test_medal_grant_notifies(self):
        admin = User.objects.create_user(username="adm", password="Str0ngPass!2025", is_staff=True, is_active=True)
        member = User.objects.create_user(username="m", password="x", is_active=True)
        medal = Medal.objects.create(name="电赛国奖", icon="🏅")
        self.client.login(username="adm", password="Str0ngPass!2025")
        self.client.post(reverse("dashboard:medals"), {
            "form": "grant", "medal_id": medal.pk, "user_id": member.pk, "reason": "2026 国一",
        })
        self.assertTrue(UserMedal.objects.filter(user=member, medal=medal).exists())
        n = member.notifications.get()
        self.assertEqual(n.kind, Notification.Kind.MEDAL)
        self.assertIn("电赛国奖", n.title)

    def test_feedback_reply_notifies_submitter(self):
        submitter = User.objects.create_user(username="sub", password="x", is_active=True)
        officer = User.objects.create_user(username="off", password="Str0ngPass!2025", is_active=True)
        officer.set_level(roles.LEVEL_OFFICER)
        fb = Feedback.objects.create(user=submitter, content="页面打不开啊啊啊")

        self.client.login(username="off", password="Str0ngPass!2025")
        self.client.post(reverse("core:feedback_detail", args=[fb.pk]), {"content": "已修复，请再试试"})
        n = submitter.notifications.get()
        self.assertEqual(n.kind, Notification.Kind.FEEDBACK)
        self.assertIn("新回复", n.title)

    def test_own_reply_does_not_notify_self(self):
        submitter = User.objects.create_user(username="sub2", password="Str0ngPass!2025", is_active=True)
        fb = Feedback.objects.create(user=submitter, content="有个小问题要补充")
        self.client.login(username="sub2", password="Str0ngPass!2025")
        self.client.post(reverse("core:feedback_detail", args=[fb.pk]), {"content": "补充：手机上也一样"})
        self.assertEqual(submitter.notifications.count(), 0)
