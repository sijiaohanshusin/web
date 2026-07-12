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
