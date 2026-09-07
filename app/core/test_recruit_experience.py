from django.core.cache import cache
from django.test import RequestFactory, TestCase

from .templatetags.navigation import nav_group


class RecruitNavigationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_guide_current_is_not_recruitment(self):
        response = self.client.get('/recruit/')
        self.assertContains(response, 'href="/recruit/" aria-current="page"')
        self.assertNotContains(response, 'href="/recruitment/" aria-current="page"')

    def test_home_current_and_group_current(self):
        self.assertContains(self.client.get('/'), 'href="/" aria-current="page"')
        self.assertContains(self.client.get('/honors/'), 'data-nav-current="true"')
        self.assertContains(self.client.get('/honors/'), 'href="/honors/" aria-current="page"')

    def test_robot_is_accessible_and_does_not_replace_form(self):
        response = self.client.get('/recruitment/')
        self.assertContains(response, 'data-recruit-robot')
        self.assertContains(response, '让小电路打个招呼')

    def test_resource_routes_select_learning_group(self):
        for path in ('/resources/', '/resources/42/', '/learn/electronics/'):
            with self.subTest(path=path):
                context = {'request': RequestFactory().get(path)}
                self.assertIn('data-nav-current="true"', nav_group(context, 'learn'))
                self.assertEqual(nav_group(context, 'about'), '')
