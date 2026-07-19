from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import SiteConfig

from . import roles, verification
from .models import Medal, Position, UserMedal, VerificationCode

User = get_user_model()

SSO_SECRET = "dev-sso-secret-not-for-production"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationTests(TestCase):
    def _set_config(self, **kw):
        c = SiteConfig.load()
        for k, v in kw.items():
            setattr(c, k, v)
        c.save()

    def _register_payload(self, **over):
        data = {
            "username": "xiaoming",
            "real_name": "小明",
            "student_id": "2025010101",
            "college": "信通学院",
            "grade": "2025",
            "email": "xm@example.com",
            "phone": "13800000001",
            "password1": "Str0ngPass!2025",
            "password2": "Str0ngPass!2025",
        }
        data.update(over)
        return data

    def _get_code(self, email, purpose):
        verification.issue(email, purpose)
        return VerificationCode.objects.filter(email=email, purpose=purpose, used=False).latest("created_at").code

    def test_register_requires_code(self):
        self._set_config(beta_mode=False, auto_approve=True)
        resp = self.client.post(reverse("accounts:register"), self._register_payload(code="000000"))
        self.assertContains(resp, "验证码")
        self.assertFalse(User.objects.filter(username="xiaoming").exists())

    def test_register_auto_approve(self):
        self._set_config(beta_mode=False, auto_approve=True)
        code = self._get_code("xm@example.com", "register")
        resp = self.client.post(reverse("accounts:register"), self._register_payload(code=code))
        self.assertEqual(resp.status_code, 302)
        u = User.objects.get(username="xiaoming")
        self.assertTrue(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_APPLICANT)

    def test_register_beta_mode_gives_officer(self):
        self._set_config(beta_mode=True, auto_approve=True)
        code = self._get_code("xm@example.com", "register")
        self.client.post(reverse("accounts:register"), self._register_payload(code=code))
        u = User.objects.get(username="xiaoming")
        self.assertEqual(u.member_level, roles.LEVEL_OFFICER)
        self.assertTrue(u.is_officer)

    def test_register_manual_review(self):
        self._set_config(beta_mode=False, auto_approve=False)
        code = self._get_code("xm@example.com", "register")
        self.client.post(reverse("accounts:register"), self._register_payload(code=code))
        u = User.objects.get(username="xiaoming")
        self.assertFalse(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_PENDING)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="a", password="x", email="dup@example.com")
        self._set_config(beta_mode=False, auto_approve=True)
        resp = self.client.post(reverse("accounts:register"), self._register_payload(email="dup@example.com", code="123456"))
        self.assertContains(resp, "该邮箱已注册")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class VerificationTests(TestCase):
    def test_issue_sends_email(self):
        verification.issue("v@example.com", "register")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("验证码", mail.outbox[0].subject)

    def test_cooldown(self):
        verification.issue("v@example.com", "register")
        ok, _ = verification.can_send("v@example.com")
        self.assertFalse(ok)

    def test_verify_wrong_then_right(self):
        code = verification.issue("v@example.com", "login").code
        with self.assertRaises(verification.CodeError):
            verification.verify("v@example.com", "login", "000000")
        verification.verify("v@example.com", "login", code)  # 不抛异常即通过

    def test_forgot_password_resets(self):
        user = User.objects.create_user(username="bob", password="OldPass!2025", email="bob@example.com", is_active=True)
        user.member_level = roles.LEVEL_FORMAL
        user.save()
        code = verification.issue("bob@example.com", "reset").code
        resp = self.client.post(reverse("accounts:forgot_password"), {
            "email": "bob@example.com", "code": code,
            "new_password1": "BrandNew!2025", "new_password2": "BrandNew!2025",
        })
        self.assertEqual(resp.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("BrandNew!2025"))


class LevelTests(TestCase):
    def test_set_level_syncs_group_and_log(self):
        u = User.objects.create_user(username="c", password="x")
        u.set_level(roles.LEVEL_OFFICER, note="test")
        self.assertTrue(u.is_active)
        self.assertTrue(u.groups.filter(name="干事").exists())
        self.assertTrue(u.is_officer)
        self.assertEqual(u.level_logs.count(), 1)

    def test_promote_removes_old_group(self):
        u = User.objects.create_user(username="d", password="x")
        u.set_level(roles.LEVEL_APPLICANT)
        self.assertTrue(u.groups.filter(name="报名会员").exists())
        u.set_level(roles.LEVEL_FORMAL)
        self.assertFalse(u.groups.filter(name="报名会员").exists())
        self.assertTrue(u.groups.filter(name="正式会员").exists())

    def test_cohort_label(self):
        u = User.objects.create_user(username="e", password="x", grade="2025")
        self.assertEqual(u.cohort_label, "25届")

    def test_admin_level_sets_staff(self):
        u = User.objects.create_user(username="f", password="x")
        u.set_level(roles.LEVEL_ADMIN)
        u.refresh_from_db()
        self.assertTrue(u.is_staff)


@override_settings(NODEBB_JWT_SECRET=SSO_SECRET)
class SsoTests(TestCase):
    def test_sso_cookie_carries_level_and_position(self):
        import jwt

        pos = Position.objects.create(name="硬件主席", color="#c98a3d")
        User.objects.create_user(username="ssou", password="Str0ngPass!2025", email="s@x.cn")
        user = User.objects.get(username="ssou")
        user.member_level = roles.LEVEL_FORMAL
        user.position = pos
        user.save()
        roles.sync_user_groups(user)

        self.client.login(username="ssou", password="Str0ngPass!2025")
        resp = self.client.get(reverse("core:home"))
        cookie = resp.cookies.get("heuesta_sso")
        self.assertIsNotNone(cookie)
        payload = jwt.decode(cookie.value, SSO_SECRET, algorithms=["HS256"])
        self.assertIn("正式会员", payload["groups"])
        self.assertIn("硬件主席", payload["groups"])


class MedalTests(TestCase):
    def test_award_medal_unique(self):
        u = User.objects.create_user(username="g", password="x")
        m = Medal.objects.create(name="电赛国奖")
        UserMedal.objects.create(user=u, medal=m)
        self.assertEqual(u.medals.count(), 1)
