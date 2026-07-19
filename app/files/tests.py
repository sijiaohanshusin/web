import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import roles

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
        self.applicant = User.objects.create_user(username="applicant", password="x")
        self.applicant.set_level(roles.LEVEL_APPLICANT)
        self.formal = User.objects.create_user(username="formal", password="x")
        self.formal.set_level(roles.LEVEL_FORMAL)
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)

        self.public_res = Resource.objects.create(
            title="公开资料", category=Resource.Category.TRAINING,
            min_level=Resource.MinLevel.PUBLIC,
            file=SimpleUploadedFile("public.txt", b"hello public"), uploader=self.officer,
        )
        self.formal_res = Resource.objects.create(
            title="正式会员资料", category=Resource.Category.CONTEST,
            min_level=Resource.MinLevel.FORMAL,
            file=SimpleUploadedFile("formal.txt", b"formal only"), uploader=self.officer,
        )

    def test_anonymous_sees_only_public(self):
        resp = self.client.get(reverse("files:list"))
        self.assertContains(resp, "公开资料")
        self.assertNotContains(resp, "正式会员资料")

    def test_applicant_cannot_see_formal(self):
        self.client.login(username="applicant", password="x")
        resp = self.client.get(reverse("files:list"))
        self.assertNotContains(resp, "正式会员资料")

    def test_formal_sees_formal(self):
        self.client.login(username="formal", password="x")
        resp = self.client.get(reverse("files:list"))
        self.assertContains(resp, "正式会员资料")

    def test_applicant_download_formal_forbidden(self):
        self.client.login(username="applicant", password="x")
        resp = self.client.get(reverse("files:download", args=[self.formal_res.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_formal_download_ok(self):
        self.client.login(username="formal", password="x")
        resp = self.client.get(reverse("files:download", args=[self.formal_res.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_download_gated_redirects_login(self):
        resp = self.client.get(reverse("files:download", args=[self.formal_res.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_applicant_cannot_upload(self):
        self.client.login(username="applicant", password="x")
        resp = self.client.get(reverse("files:upload"))
        self.assertEqual(resp.status_code, 302)

    def test_officer_can_upload(self):
        self.client.login(username="officer", password="x")
        resp = self.client.post(reverse("files:upload"), {
            "title": "新课件", "description": "培训",
            "category": Resource.Category.TRAINING,
            "min_level": Resource.MinLevel.PUBLIC,
            "file": SimpleUploadedFile("s.pdf", b"%PDF-1.4 x"),
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Resource.objects.filter(title="新课件").exists())
