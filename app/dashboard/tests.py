from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.roles import GROUP_MEMBER, GROUP_OFFICER

User = get_user_model()


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="x")
        self.member.groups.add(Group.objects.get(name=GROUP_MEMBER))
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.groups.add(Group.objects.get(name=GROUP_OFFICER))
        self.admin = User.objects.create_user(username="staff", password="x", is_staff=True)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_plain_member_forbidden(self):
        self.client.login(username="member", password="x")
        resp = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(resp.status_code, 403)

    def test_officer_can_view_overview_and_members(self):
        self.client.login(username="officer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:members")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:resources")).status_code, 200)

    def test_officer_forbidden_from_site_settings(self):
        self.client.login(username="officer", password="x")
        resp = self.client.get(reverse("dashboard:site_settings"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_view_site_settings(self):
        self.client.login(username="staff", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:site_settings")).status_code, 200)


class MemberActionTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.groups.add(Group.objects.get(name=GROUP_OFFICER))
        self.admin = User.objects.create_user(username="staff", password="x", is_staff=True)
        self.pending = User.objects.create_user(username="newbie", password="x")
        self.pending.is_active = False
        self.pending.save()

    def test_officer_can_batch_approve(self):
        self.client.login(username="officer", password="x")
        resp = self.client.post(reverse("dashboard:member_action"), {
            "action": "approve",
            "ids": [self.pending.pk],
        })
        self.assertEqual(resp.status_code, 302)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertTrue(self.pending.groups.filter(name=GROUP_MEMBER).exists())

    def test_officer_cannot_reject_delete(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {
            "action": "reject_delete",
            "ids": [self.pending.pk],
        })
        self.assertTrue(User.objects.filter(pk=self.pending.pk).exists())

    def test_admin_can_reject_delete(self):
        self.client.login(username="staff", password="x")
        self.client.post(reverse("dashboard:member_action"), {
            "action": "reject_delete",
            "ids": [self.pending.pk],
        })
        self.assertFalse(User.objects.filter(pk=self.pending.pk).exists())

    def test_admin_can_make_officer(self):
        active_user = User.objects.create_user(username="active", password="x")
        active_user.groups.add(Group.objects.get(name=GROUP_MEMBER))
        self.client.login(username="staff", password="x")
        self.client.post(reverse("dashboard:member_action"), {
            "action": "make_officer",
            "ids": [active_user.pk],
        })
        self.assertTrue(active_user.groups.filter(name=GROUP_OFFICER).exists())
