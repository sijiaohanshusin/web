from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from . import roles

User = get_user_model()


class RegistrationTests(TestCase):
    def test_register_creates_inactive_user(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "xiaoming",
            "real_name": "小明",
            "student_id": "2025010101",
            "college": "信通学院",
            "grade": "2025",
            "qq": "12345678",
            "password1": "Str0ngPass!2025",
            "password2": "Str0ngPass!2025",
        })
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(username="xiaoming")
        self.assertFalse(user.is_active)

    def test_duplicate_student_id_rejected(self):
        User.objects.create_user(username="a", password="x", student_id="2025010101")
        resp = self.client.post(reverse("accounts:register"), {
            "username": "b",
            "real_name": "小红",
            "student_id": "2025010101",
            "college": "信通学院",
            "grade": "2025",
            "password1": "Str0ngPass!2025",
            "password2": "Str0ngPass!2025",
        })
        self.assertContains(resp, "该学号已注册")
        self.assertFalse(User.objects.filter(username="b").exists())

    def test_pending_user_login_shows_review_message(self):
        user = User.objects.create_user(username="pending", password="Str0ngPass!2025")
        user.is_active = False
        user.save()
        resp = self.client.post(reverse("accounts:login"), {
            "username": "pending",
            "password": "Str0ngPass!2025",
        })
        self.assertContains(resp, "等待管理员审核")

    def test_active_user_can_login(self):
        User.objects.create_user(username="active", password="Str0ngPass!2025")
        resp = self.client.post(reverse("accounts:login"), {
            "username": "active",
            "password": "Str0ngPass!2025",
        }, follow=True)
        self.assertTrue(resp.context["user"].is_authenticated)


class SsoCookieTests(TestCase):
    """论坛账号互通：登录发 heuesta_sso JWT Cookie，登出清除。"""

    SECRET = "dev-sso-secret-not-for-production"

    def setUp(self):
        self.user = User.objects.create_user(username="ssouser", password="Str0ngPass!2025", email="s@x.cn")
        self.user.real_name = "宋九"
        self.user.save()

    def test_login_sets_sso_cookie_with_valid_jwt(self):
        import jwt

        resp = self.client.post(reverse("accounts:login"), {
            "username": "ssouser",
            "password": "Str0ngPass!2025",
        })
        self.assertEqual(resp.status_code, 302)
        cookie = resp.cookies.get("heuesta_sso")
        self.assertIsNotNone(cookie)
        payload = jwt.decode(cookie.value, self.SECRET, algorithms=["HS256"])
        self.assertEqual(payload["id"], self.user.pk)
        self.assertEqual(payload["username"], "ssouser")
        self.assertEqual(payload["fullname"], "宋九")
        self.assertEqual(payload["email"], "s@x.cn")
        self.assertEqual(payload["groups"], [])

    def test_sso_payload_contains_role_groups(self):
        import jwt
        from django.contrib.auth.models import Group

        self.user.groups.add(Group.objects.get(name="会员"), Group.objects.get(name="干事"))
        resp = self.client.post(reverse("accounts:login"), {
            "username": "ssouser",
            "password": "Str0ngPass!2025",
        })
        payload = jwt.decode(resp.cookies["heuesta_sso"].value, self.SECRET, algorithms=["HS256"])
        self.assertEqual(payload["groups"], ["会员", "干事"])

    def test_logout_clears_sso_cookie(self):
        self.client.login(username="ssouser", password="Str0ngPass!2025")
        self.client.cookies["heuesta_sso"] = "whatever"
        resp = self.client.post(reverse("accounts:logout"))
        cookie = resp.cookies.get("heuesta_sso")
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, "")  # 删除 = 置空 + 过期

    def test_anonymous_with_stale_cookie_gets_it_removed(self):
        self.client.cookies["heuesta_sso"] = "stale-token"
        resp = self.client.get(reverse("core:home"))
        cookie = resp.cookies.get("heuesta_sso")
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, "")

    def test_valid_cookie_not_reissued(self):
        self.client.login(username="ssouser", password="Str0ngPass!2025")
        first = self.client.get(reverse("core:home")).cookies.get("heuesta_sso")
        self.assertIsNotNone(first)
        # 带着有效 Cookie 再请求，不应重新签发
        self.client.cookies["heuesta_sso"] = first.value
        second = self.client.get(reverse("core:home")).cookies.get("heuesta_sso")
        self.assertIsNone(second)


class RoleTests(TestCase):
    def test_groups_created_by_migration(self):
        for name in roles.ALL_GROUPS:
            self.assertTrue(Group.objects.filter(name=name).exists(), name)

    def test_member_and_officer_helpers(self):
        member = User.objects.create_user(username="m", password="x")
        member.groups.add(Group.objects.get(name=roles.GROUP_MEMBER))
        officer = User.objects.create_user(username="o", password="x")
        officer.groups.add(Group.objects.get(name=roles.GROUP_OFFICER))

        self.assertTrue(roles.is_member(member))
        self.assertFalse(roles.is_officer(member))
        self.assertTrue(roles.is_member(officer))
        self.assertTrue(roles.is_officer(officer))
