from django.test import TestCase
from django.urls import reverse

from accounts import roles
from accounts.models import Medal, User, UserMedal
from notify.models import Notification


class MedalGrantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="medal-admin", is_staff=True)
        cls.member = User.objects.create_user(
            username="小林+maker", real_name="测试林同学", student_id="2026999901",
            member_level=roles.LEVEL_FORMAL,
        )
        cls.medal = Medal.objects.create(name="测试贡献勋章")

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("dashboard:medals")

    def grant(self, identifier=None, **overrides):
        data = {
            "form": "grant", "medal_id": str(self.medal.pk),
            "user_id": identifier or str(self.member.pk), "reason": "帮助完成测试",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_supported_identifiers_resolve_the_same_member(self):
        for identifier in (
            self.member.username, self.member.student_id, self.member.real_name,
            f"#{self.member.pk}", str(self.member.pk),
        ):
            with self.subTest(identifier=identifier):
                response = self.grant(identifier)
                self.assertRedirects(response, self.url)
                self.assertEqual(UserMedal.objects.get().user_id, self.member.pk)
                UserMedal.objects.all().delete()

    def test_unknown_member_retains_form_values_instead_of_404(self):
        response = self.grant("2026999999")
        self.assertContains(response, "没找到成员")
        self.assertContains(response, 'value="2026999999"')
        self.assertContains(response, 'value="帮助完成测试"')
        self.assertContains(response, f'value="{self.medal.pk}" selected')
        self.assertFalse(UserMedal.objects.exists())

    def test_empty_identifier_is_a_form_error(self):
        response = self.grant(user_id="")
        self.assertContains(response, "请填写要操作的成员")
        self.assertFalse(UserMedal.objects.exists())

    def test_ambiguous_name_never_grants_to_an_arbitrary_member(self):
        User.objects.create_user(username="another-member", real_name=self.member.real_name)
        response = self.grant(self.member.real_name)
        self.assertContains(response, "请改用用户名或学号")
        self.assertContains(response, f'value="{self.member.real_name}"')
        self.assertFalse(UserMedal.objects.exists())

    def test_invalid_medal_is_a_recoverable_form_error(self):
        for value in ("", "not-an-id", "99999999999999999999999999", "-1", "999999999"):
            with self.subTest(value=value):
                response = self.grant(medal_id=value)
                self.assertContains(response, "请选择仍然存在的勋章")
                self.assertContains(response, 'value="帮助完成测试"')
                self.assertFalse(UserMedal.objects.exists())

    def test_reason_length_is_validated_on_server(self):
        response = self.grant(reason="长" * 201)
        self.assertContains(response, "授予理由不能超过 200 字")
        self.assertFalse(UserMedal.objects.exists())

    def test_reason_at_limit_is_accepted(self):
        self.assertRedirects(self.grant(reason="长" * 200), self.url)
        self.assertEqual(UserMedal.objects.get().reason, "长" * 200)

    def test_retained_input_is_escaped(self):
        response = self.grant('<img src=x onerror="alert(1)">', reason='" autofocus onfocus="alert(1)')
        self.assertContains(response, "&lt;img")
        self.assertContains(response, "&quot; autofocus")
        self.assertNotContains(response, '<img src=x')
        self.assertFalse(UserMedal.objects.exists())

    def test_duplicate_grant_notifies_once_and_does_not_change_membership(self):
        for _ in range(2):
            self.assertRedirects(self.grant(), self.url)
        self.assertEqual(UserMedal.objects.count(), 1)
        self.assertEqual(self.member.notifications.filter(kind=Notification.Kind.MEDAL).count(), 1)
        self.member.refresh_from_db()
        self.assertEqual(self.member.member_level, roles.LEVEL_FORMAL)
        self.assertFalse(self.member.is_staff)
        self.assertIsNone(self.member.position_id)

    def test_officer_cannot_grant(self):
        officer = User.objects.create_user(username="medal-officer", member_level=roles.LEVEL_OFFICER)
        self.client.force_login(officer)
        self.assertEqual(self.grant().status_code, 403)
        self.assertFalse(UserMedal.objects.exists())
