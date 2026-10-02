from unittest.mock import patch
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse
from core import bilibili


class LaunchQualityTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_cold_home_never_calls_bilibili(self):
        with patch("core.bilibili.requests.get", side_effect=AssertionError("network on request path")) as get:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        get.assert_not_called()
        self.assertNotContains(response, "27 章")
        self.assertContains(response, "跳过开场")

    def test_refresh_failure_keeps_successful_snapshot(self):
        previous = {"title": "已核对的视频", "bvid": "BV123"}
        cache.set("bili:video:BV123", previous, timeout=None)
        with patch("core.bilibili._get_json", return_value=None):
            self.assertEqual(bilibili.get_video_info("BV123", refresh=True), previous)
        self.assertEqual(bilibili.get_video_info("BV123"), previous)

    def test_readiness_depends_only_on_database(self):
        with patch("core.bilibili.requests.get", side_effect=AssertionError("external request")):
            self.assertEqual(self.client.get(reverse("core:readiness")).json(), {"status": "ok"})
        with patch("django.db.connection.cursor", side_effect=DatabaseError("down")):
            response = self.client.get(reverse("core:readiness"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("down", response.content.decode())

    def test_guide_hides_production_briefs_and_invalid_deadlines(self):
        response = self.client.get("/recruit/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "11 月 31 日")
        self.assertNotContains(response, "抓拍胜过摆拍")
        self.assertContains(response, 'class="rg-details"', count=5)

    def test_sitemap_excludes_drafts_and_member_news(self):
        from news.models import Post
        public = Post.objects.create(title="公开", body="正文", min_level=0)
        private = Post.objects.create(title="会员", body="正文", min_level=3)
        draft = Post.objects.create(title="草稿", body="正文", is_published=False)
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, public.get_absolute_url())
        self.assertNotContains(response, private.get_absolute_url())
        self.assertNotContains(response, draft.get_absolute_url())
        self.assertNotContains(response, "/learn/")
        public.is_published = False
        public.save()
        self.assertNotContains(self.client.get("/sitemap.xml"), public.get_absolute_url())

    def test_canonical_omits_queries_and_does_not_trust_host(self):
        response = self.client.get("/recruit/?next=/accounts/login/", HTTP_HOST="testserver")
        self.assertContains(response, '<link rel="canonical" href="https://heuesta.cn/recruit/">')
        self.assertEqual(self.client.get("/accounts/login/")["X-Robots-Tag"], "noindex, nofollow")
