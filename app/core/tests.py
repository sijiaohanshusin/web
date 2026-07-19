from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import roles

from .models import Feedback

User = get_user_model()

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class FeedbackTests(TestCase):
    def test_page_renders(self):
        resp = self.client.get(reverse("core:feedback"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "内测反馈")

    def test_ajax_submit_creates_record(self):
        resp = self.client.post(reverse("core:feedback"), {
            "content": "注册页验证码按钮在手机上显示不全",
            "page": "https://heuesta.cn/accounts/register/",
            "contact": "qq:12345",
        }, **AJAX, REMOTE_ADDR="10.1.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        fb = Feedback.objects.get()
        self.assertEqual(fb.status, Feedback.Status.PENDING)
        self.assertEqual(fb.contact, "qq:12345")
        self.assertIsNone(fb.user)

    def test_short_content_rejected(self):
        resp = self.client.post(reverse("core:feedback"), {"content": "卡了"}, **AJAX, REMOTE_ADDR="10.1.0.2")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_cooldown_throttles(self):
        payload = {"content": "第一次提交的反馈内容够长了"}
        self.client.post(reverse("core:feedback"), payload, **AJAX, REMOTE_ADDR="10.1.0.3")
        resp = self.client.post(reverse("core:feedback"), payload, **AJAX, REMOTE_ADDR="10.1.0.3")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("频繁", resp.json()["msg"])
        self.assertEqual(Feedback.objects.count(), 1)

    def test_logged_in_user_attached(self):
        user = User.objects.create_user(username="fbuser", password="x")
        user.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="fbuser", password="x")
        self.client.post(reverse("core:feedback"), {"content": "登录用户提交的反馈内容"}, **AJAX, REMOTE_ADDR="10.1.0.4")
        self.assertEqual(Feedback.objects.get().user, user)


class FeedbackDashboardTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="off", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.fb = Feedback.objects.create(content="测试反馈内容", contact="qq:1")

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("dashboard:feedbacks"))
        self.assertEqual(resp.status_code, 302)

    def test_officer_sees_list(self):
        self.client.login(username="off", password="x")
        resp = self.client.get(reverse("dashboard:feedbacks"))
        self.assertContains(resp, "测试反馈内容")

    def test_resolve_flow(self):
        self.client.login(username="off", password="x")
        self.client.post(reverse("dashboard:feedbacks"), {
            "action": "resolve", "id": self.fb.pk, "note": "已修复",
        })
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, Feedback.Status.RESOLVED)
        self.assertEqual(self.fb.admin_note, "已修复")
        self.assertEqual(self.fb.resolved_by, self.officer)
