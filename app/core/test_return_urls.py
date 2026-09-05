from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import Feedback
from events.models import Event
from news.models import Post
from notify.services import notify_user
from projects.models import Project


class ReturnUrlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='return-url-admin', is_staff=True, member_level=5)
        cls.feedback = Feedback.objects.create(user=cls.admin, content='Return URL test')
        cls.post = Post.objects.create(title='Return URL test', body='Test', author=cls.admin)
        cls.event = Event.objects.create(title='Return URL test', description='Test',
                                        start_at=timezone.now(), end_at=timezone.now(), created_by=cls.admin)
        cls.project = Project.objects.create(name='Return URL test', created_by=cls.admin)

    def setUp(self):
        self.client.force_login(self.admin)
        self.routes = (
            (reverse('notify:read_all'), {}, reverse('notify:list')),
            (reverse('core:feedback_detail', args=[self.feedback.pk]), {'content': 'Test reply'},
             reverse('core:feedback_detail', args=[self.feedback.pk])),
            (reverse('dashboard:feedbacks'), {'id': self.feedback.pk, 'action': 'resolve'}, reverse('dashboard:feedbacks')),
            (reverse('dashboard:news'), {'id': self.post.pk, 'action': 'pin'}, reverse('dashboard:news')),
            (reverse('dashboard:events'), {'id': self.event.pk, 'action': 'toggle_publish'}, reverse('dashboard:events')),
            (reverse('dashboard:projects'), {'id': self.project.pk, 'action': 'archive'}, reverse('dashboard:projects')),
            (reverse('dashboard:member_action'), {'action': 'promote_prep'}, reverse('dashboard:members')),
        )

    def test_post_return_urls_reject_external_or_malformed_targets(self):
        for target in ('https://outside.example/', '//outside.example/', '/\\outside.example/',
                       'javascript:alert(1)', 'not-a-route', '/notify/\r\nX-Test: bad'):
            for route, payload, fallback in self.routes:
                with self.subTest(route=route, target=repr(target)):
                    response = self.client.post(route, {**payload, 'next': target})
                    self.assertRedirects(response, fallback, fetch_redirect_response=False)

    def test_post_return_urls_preserve_same_site_filters(self):
        for target in ('/notify/?tab=unread&page=2#list', 'https://testserver/notify/?tab=all'):
            for route, payload, _ in self.routes:
                with self.subTest(route=route, target=target):
                    response = self.client.post(route, {**payload, 'next': target}, secure=True)
                    self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_https_return_cannot_downgrade_connection(self):
        for route, payload, fallback in self.routes:
            with self.subTest(route=route):
                response = self.client.post(route, {**payload, 'next': 'http://testserver/notify/'}, secure=True)
                self.assertRedirects(response, fallback, fetch_redirect_response=False)

    def test_notification_target_cannot_leave_site(self):
        for target in ('//outside.example/', '/\\outside.example/', '/notify/\r\nX-Test: bad'):
            with self.subTest(target=repr(target)):
                note = notify_user(self.admin, 'Test notification', url=target)
                response = self.client.get(reverse('notify:go', args=[note.pk]))
                self.assertRedirects(response, reverse('notify:list'), fetch_redirect_response=False)
                note.refresh_from_db()
                self.assertTrue(note.is_read)

    def test_login_return_rejects_non_url_without_server_error(self):
        response = self.client.get(reverse('accounts:login'), {'next': 'not-a-route'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_login_return_keeps_valid_member_destination(self):
        response = self.client.get(reverse('accounts:login'), {'next': '/accounts/profile/'})
        self.assertRedirects(response, '/accounts/profile/', fetch_redirect_response=False)

    def test_logout_with_invalid_return_still_ends_session(self):
        response = self.client.post(reverse('accounts:logout'), {'next': 'not-a-route'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
