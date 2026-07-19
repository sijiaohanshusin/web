from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import roles

User = get_user_model()


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.applicant = User.objects.create_user(username="applicant", password="x")
        self.applicant.set_level(roles.LEVEL_APPLICANT)
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.admin = User.objects.create_user(username="admin1", password="x")
        self.admin.set_level(roles.LEVEL_ADMIN)

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_applicant_forbidden(self):
        self.client.login(username="applicant", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 403)

    def test_officer_can_view(self):
        self.client.login(username="officer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:members")).status_code, 200)

    def test_officer_forbidden_from_medals(self):
        self.client.login(username="officer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:medals")).status_code, 403)

    def test_admin_can_view_medals_positions_site(self):
        self.client.login(username="admin1", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:medals")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:positions")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:site_settings")).status_code, 200)


class MemberActionTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.admin = User.objects.create_user(username="admin1", password="x")
        self.admin.set_level(roles.LEVEL_ADMIN)
        self.pending = User.objects.create_user(username="newbie", password="x", is_active=False)

    def test_officer_can_approve(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "approve", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_APPLICANT)
        self.assertTrue(self.pending.is_active)

    def test_officer_can_promote_formal(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "promote_formal", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_FORMAL)

    def test_officer_cannot_make_admin(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "make_admin", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertNotEqual(self.pending.member_level, roles.LEVEL_ADMIN)

    def test_admin_can_make_officer(self):
        self.client.login(username="admin1", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "make_officer", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_OFFICER)

    def test_admin_reject_delete(self):
        self.client.login(username="admin1", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "reject_delete", "ids": [self.pending.pk]})
        self.assertFalse(User.objects.filter(pk=self.pending.pk).exists())
