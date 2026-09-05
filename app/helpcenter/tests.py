from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import resolve

from accounts.models import User
from . import content
from .views import rendered


class HelpAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user(username="help-officer", member_level=4)
        cls.admin = User.objects.create_user(username="help-admin", member_level=5)
        cls.recruit = User.objects.create_user(username="help-recruit", member_level=1)

    def test_public_catalog_does_not_leak_internal_articles(self):
        for url in ("/help/", "/help/search/?q=站点设置"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'href="/help/admin/settings/"')
            self.assertNotContains(response, 'href="/help/admin/"')
        for path in ("/help/admin/", "/help/admin/settings/", "/help/admin/members/"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_officer_only_receives_executable_chapters(self):
        self.client.force_login(self.officer)
        response = self.client.get("/help/admin/")
        self.assertContains(response, '/help/admin/review/')
        self.assertNotContains(response, '/help/admin/settings/')
        self.assertNotContains(response, '/help/admin/positions/')
        self.assertEqual(self.client.get('/help/admin/positions/').status_code, 404)
        self.assertNotContains(self.client.get('/help/search/?q=安全规则'), '/help/admin/settings/')
        self.assertIn('noindex', response['X-Robots-Tag'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('Cookie', response['Vary'])

    def test_admin_chapters_and_screenshots_follow_same_permission(self):
        item = content.find(self.admin, 'admin', 'settings')
        image_url = item.url + 'images/' + item.screenshots[0] + '/'
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(item.url), item.title)
        image = self.client.get(image_url)
        self.assertEqual(image.status_code, 200)
        self.assertIn('no-store', image['Cache-Control'])
        image.close()
        other_url = '/help/recruit/channel/images/' + item.screenshots[0] + '/'
        self.assertEqual(self.client.get(other_url).status_code, 404)

    def test_disabled_account_loses_all_internal_help(self):
        self.admin.is_active = False
        self.assertFalse(content.allowed(self.admin, 'admin'))
        self.assertEqual(content.visible(self.admin, 'admin'), [])

    def test_public_guides_remain_available_to_recruit_and_guest(self):
        for user in (None, self.recruit):
            if user:
                self.client.force_login(user)
            for audience in ('recruit', 'member'):
                self.assertEqual(self.client.get(f'/help/{audience}/').status_code, 200)
                for item in content.visible(AnonymousUser(), audience):
                    with self.subTest(item=item.key):
                        page = self.client.get(item.url)
                        self.assertEqual(page.status_code, 200)
                        self.assertNotIn('X-Robots-Tag', page)

    def test_search_handles_chinese_and_escapes_query(self):
        self.assertContains(self.client.get('/help/search/', {'q': '验证码'}), '/help/recruit/verify/')
        page = self.client.get('/help/search/', {'q': '<script>alert(1)</script>'})
        self.assertNotContains(page, '<script>alert(1)</script>')

    def test_source_links_and_images_exist_and_do_not_use_public_static_paths(self):
        self.assertGreaterEqual(len(content.articles()), 43)
        for article in content.articles():
            with self.subTest(article=article.key):
                self.assertTrue(article.checkpoints)
                html, toc = rendered(article)
                self.assertNotIn('asset:', html)
                for shot in article.screenshots:
                    self.assertTrue((content.ROOT / 'assets' / shot).is_file(), shot)
                    self.assertFalse((content.ROOT.parent / 'static' / 'help' / shot).exists())
                for route in article.routes:
                    if route.startswith('/'):
                        resolve(route.split('?')[0])

    def test_unknown_articles_and_images_are_404(self):
        for path in ('/help/unknown/', '/help/recruit/unknown/', '/help/recruit/channel/images/missing.png/'):
            self.assertEqual(self.client.get(path).status_code, 404)
