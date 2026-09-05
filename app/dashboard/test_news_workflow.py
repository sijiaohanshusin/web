from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from news.models import Post


class NewsWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('news-workflow-officer', member_level=4)
        cls.recruit = User.objects.create_user('news-workflow-recruit', member_level=1)

    def setUp(self):
        self.client.force_login(self.officer)

    def data(self, *, published=True, future=False):
        date = timezone.localtime() + timedelta(days=2 if future else -1)
        data = {
            'title': '隔离验收公告', 'body': '仅用于测试的正文',
            'category': 'notice', 'min_level': '0',
            'published_at': date.strftime('%Y-%m-%dT%H:%M'),
        }
        if published:
            data['is_published'] = 'on'
        return data

    def test_unpublished_save_does_not_claim_to_be_published(self):
        response = self.client.post(reverse('dashboard:news_create'), self.data(published=False), follow=True)
        self.assertContains(response, '已保存为未发布')
        self.assertNotContains(response, '已发布。')
        post = Post.objects.get()
        self.assertFalse(post.is_published)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 200)
        self.client.force_login(self.recruit)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 403)
        self.assertNotContains(self.client.get('/news/'), post.title)

    def test_future_save_and_toggle_show_scheduled_state(self):
        response = self.client.post(reverse('dashboard:news_create'), self.data(future=True), follow=True)
        self.assertContains(response, '已保存，等待定时发布')
        self.assertContains(response, '待定时发布')
        self.assertNotContains(response, '>已发布</span>', html=False)
        post = Post.objects.get()
        for expected in ('已下架', '等待定时发布'):
            response = self.client.post(reverse('dashboard:news'), {'id': post.pk, 'action': 'toggle_publish'}, follow=True)
            self.assertContains(response, expected)
        self.client.force_login(self.recruit)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 403)

    def test_immediate_publish_and_withdraw_match_reader_access(self):
        response = self.client.post(reverse('dashboard:news_create'), self.data(), follow=True)
        self.assertContains(response, '已发布')
        post = Post.objects.get()
        self.client.force_login(self.recruit)
        self.assertContains(self.client.get(post.get_absolute_url()), post.body)
        self.client.force_login(self.officer)
        self.client.post(reverse('dashboard:news'), {'id': post.pk, 'action': 'toggle_publish'})
        self.client.force_login(self.recruit)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 403)

    def test_save_button_does_not_promise_publication(self):
        response = self.client.get(reverse('dashboard:news_create'))
        self.assertContains(response, '保存公告')
        self.assertContains(response, '取消勾选')

    def test_invalid_form_retains_body_and_never_creates_post(self):
        data = self.data()
        data['title'] = ''
        response = self.client.post(reverse('dashboard:news_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, data['body'])
        self.assertFalse(Post.objects.exists())

    def test_recruit_cannot_publish_using_direct_post(self):
        self.client.force_login(self.recruit)
        self.assertEqual(self.client.post(reverse('dashboard:news_create'), self.data()).status_code, 403)
        self.assertFalse(Post.objects.exists())
