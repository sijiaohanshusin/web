from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from . import roles, verification
from .models import Medal, Position, ReturningMembershipRequest, UserMedal, VerificationCode

User = get_user_model()

SSO_SECRET = "dev-sso-secret-not-for-production"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationTests(TestCase):
    def _register_payload(self, **over):
        data = {
            "username": "xiaoming",
            "real_name": "小明",
            "student_id": "2025010101",
            "college": "信息与通信工程学院",
            "grade": "2025",
            "email": "xm@example.com",
            "phone": "13800000001",
            "qq": "1081376858",
            "specialty": User.Specialty.HARDWARE,
            "specialty_custom": "",
            "privacy_consent": "on",
            "password1": "Str0ngPass!2025",
            "password2": "Str0ngPass!2025",
        }
        data.update(over)
        return data

    def _get_code(self, email, purpose):
        verification.issue(email, purpose)
        return VerificationCode.objects.filter(email=email, purpose=purpose, used=False).latest("created_at").code

    def test_register_requires_code(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(code="000000"))
        self.assertContains(resp, "验证码")
        self.assertFalse(User.objects.filter(username="xiaoming").exists())

    def test_register_entry_is_channel_choice(self):
        resp = self.client.get(reverse("accounts:register"))
        self.assertContains(resp, "新会员通道")
        self.assertContains(resp, "老会员通道")
        self.assertIn("no-cache", resp.headers["Cache-Control"])

    def test_new_member_registers_active_at_recruit_level(self):
        code = self._get_code("xm@example.com", "register")
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(code=code))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("recruitment:index"))
        u = User.objects.get(username="xiaoming")
        self.assertTrue(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_APPLICANT)
        self.assertEqual(u.registration_channel, User.RegistrationChannel.NEW)
        self.assertIn("_auth_user_id", self.client.session)

    def test_returning_member_waits_for_review(self):
        code = self._get_code("xm@example.com", "register")
        resp = self.client.post(reverse("accounts:register_returning"), self._register_payload(
            code=code,
            requested_role=ReturningMembershipRequest.RequestedRole.HARDWARE_VICE_CHAIR,
        ))
        self.assertEqual(resp.status_code, 200)
        u = User.objects.get(username="xiaoming")
        self.assertFalse(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_PENDING)
        self.assertEqual(u.registration_channel, User.RegistrationChannel.RETURNING)
        self.assertEqual(
            u.returning_request.requested_role,
            ReturningMembershipRequest.RequestedRole.HARDWARE_VICE_CHAIR,
        )

    def test_custom_specialty_requires_description(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(
            specialty=User.Specialty.CUSTOM,
            specialty_custom="",
            code="000000",
        ))
        self.assertContains(resp, "请填写具体方向")

    def test_grade_and_college_are_fixed_choices(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(
            grade="2023级", college="信通学院", code="000000",
        ))
        self.assertContains(resp, "选择一个有效的选项", count=2)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="a", password="x", email="dup@example.com")
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(email="dup@example.com", code="123456"))
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
        self.assertTrue(u.groups.filter(name="站务管理").exists())
        self.assertTrue(u.is_officer)
        self.assertEqual(u.level_logs.count(), 1)

    def test_promote_removes_old_group(self):
        u = User.objects.create_user(username="d", password="x")
        u.set_level(roles.LEVEL_APPLICANT)
        self.assertTrue(u.groups.filter(name="招新成员").exists())
        u.set_level(roles.LEVEL_FORMAL)
        self.assertFalse(u.groups.filter(name="招新成员").exists())
        self.assertTrue(u.groups.filter(name="科协会员").exists())

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

        pos = Position.objects.get(name="硬件主席")
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
        self.assertIn("科协会员", payload["groups"])
        self.assertIn("硬件主席", payload["groups"])

    def test_recruit_member_gets_no_forum_cookie(self):
        user = User.objects.create_user(username="recruit", password="Str0ngPass!2025")
        user.set_level(roles.LEVEL_APPLICANT)
        self.client.login(username="recruit", password="Str0ngPass!2025")
        resp = self.client.get(reverse("core:home"))
        self.assertIsNone(resp.cookies.get("heuesta_sso"))


class MedalTests(TestCase):
    def test_award_medal_unique(self):
        u = User.objects.create_user(username="g", password="x")
        m = Medal.objects.create(name="电赛国奖")
        UserMedal.objects.create(user=u, medal=m)
        self.assertEqual(u.medals.count(), 1)
