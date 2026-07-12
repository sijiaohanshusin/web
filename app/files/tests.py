import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.roles import GROUP_MEMBER, GROUP_OFFICER

from .models import Resource

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp(prefix="heuesta-test-media-")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ResourceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.member = User.objects.create_user(username="member", password="x")
        self.member.groups.add(Group.objects.get(name=GROUP_MEMBER))
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.groups.add(Group.objects.get(name=GROUP_OFFICER))

        self.public_res = Resource.objects.create(
            title="公开资料",
            category=Resource.Category.TRAINING,
            visibility=Resource.Visibility.PUBLIC,
            file=SimpleUploadedFile("public.txt", b"hello public"),
            uploader=self.officer,
        )
        self.member_res = Resource.objects.create(
            title="会员资料",
            category=Resource.Category.CONTEST,
            visibility=Resource.Visibility.MEMBERS,
            file=SimpleUploadedFile("members.txt", b"hello members"),
            uploader=self.officer,
        )

    def test_anonymous_sees_only_public(self):
        resp = self.client.get(reverse("files:list"))
        self.assertContains(resp, "公开资料")
        self.assertNotContains(resp, "会员资料")

    def test_member_sees_all(self):
        self.client.login(username="member", password="x")
        resp = self.client.get(reverse("files:list"))
        self.assertContains(resp, "公开资料")
        self.assertContains(resp, "会员资料")

    def test_anonymous_download_members_redirects_to_login(self):
        resp = self.client.get(reverse("files:download", args=[self.member_res.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_member_can_download_members_file(self):
        self.client.login(username="member", password="x")
        resp = self.client.get(reverse("files:download", args=[self.member_res.pk]))
        self.assertEqual(resp.status_code, 200)
        self.member_res.refresh_from_db()
        self.assertEqual(self.member_res.download_count, 1)

    def test_member_cannot_upload(self):
        self.client.login(username="member", password="x")
        resp = self.client.get(reverse("files:upload"))
        self.assertEqual(resp.status_code, 302)  # 被拒重定向到登录页

    def test_officer_can_upload(self):
        self.client.login(username="officer", password="x")
        resp = self.client.post(reverse("files:upload"), {
            "title": "新培训课件",
            "description": "第一次培训",
            "category": Resource.Category.TRAINING,
            "visibility": Resource.Visibility.PUBLIC,
            "file": SimpleUploadedFile("slides.pdf", b"%PDF-1.4 fake"),
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        new = Resource.objects.get(title="新培训课件")
        self.assertEqual(new.uploader, self.officer)
        self.assertGreater(new.size, 0)

    def test_search_and_category_filter(self):
        resp = self.client.get(reverse("files:list"), {"q": "公开"})
        self.assertContains(resp, "公开资料")
        resp = self.client.get(reverse("files:list"), {"category": "contest"})
        self.assertNotContains(resp, "公开资料")
