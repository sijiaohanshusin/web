from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import roles

from .markdown import render_markdown
from .models import Post

User = get_user_model()


def make_post(**kw):
    defaults = {"title": "测试公告", "body": "正文内容", "category": Post.Category.NOTICE}
    defaults.update(kw)
    return Post.objects.create(**defaults)


class MarkdownTests(TestCase):
    def test_renders_basic_markdown(self):
        html = render_markdown("# 标题\n\n**加粗** 和 [链接](https://heuesta.cn)")
        self.assertIn("<h1>", html)
        self.assertIn("<strong>", html)
        self.assertIn('href="https://heuesta.cn"', html)

    def test_strips_script(self):
        html = render_markdown('正常内容 <script>alert("xss")</script>')
        self.assertNotIn("<script>", html)
        self.assertIn("正常内容", html)

    def test_strips_event_handlers(self):
        html = render_markdown('<img src="/a.png" onerror="alert(1)">')
        self.assertNotIn("onerror", html)

    def test_empty(self):
        self.assertEqual(render_markdown(""), "")


class NewsListTests(TestCase):
    def test_public_sees_only_public_published(self):
        make_post(title="公开公告")
        make_post(title="会员公告", min_level=Post.MinLevel.FORMAL)
        make_post(title="下架公告", is_published=False)
        make_post(title="未来公告", published_at=timezone.now() + timezone.timedelta(days=1))

        resp = self.client.get(reverse("news:list"))
        self.assertContains(resp, "公开公告")
        self.assertNotContains(resp, "会员公告")
        self.assertNotContains(resp, "下架公告")
        self.assertNotContains(resp, "未来公告")

    def test_member_sees_level_gated(self):
        make_post(title="会员公告", min_level=Post.MinLevel.FORMAL)
        u = User.objects.create_user(username="m", password="Str0ngPass!2025", is_active=True)
        u.set_level(roles.LEVEL_FORMAL)
        self.client.login(username="m", password="Str0ngPass!2025")
        resp = self.client.get(reverse("news:list"))
        self.assertContains(resp, "会员公告")

    def test_category_filter(self):
        make_post(title="通知一则", category=Post.Category.NOTICE)
        make_post(title="喜报一则", category=Post.Category.HONOR)
        resp = self.client.get(reverse("news:list"), {"category": "honor"})
        self.assertContains(resp, "喜报一则")
        self.assertNotContains(resp, "通知一则")

    def test_pinned_first(self):
        make_post(title="普通")
        pinned = make_post(title="置顶", pinned=True)
        self.assertEqual(Post.objects.first().pk, pinned.pk)


class NewsDetailTests(TestCase):
    def test_detail_renders_markdown(self):
        p = make_post(body="## 小标题\n\n- 条目一\n- 条目二")
        resp = self.client.get(reverse("news:detail", args=[p.pk]))
        self.assertContains(resp, "<h2>小标题</h2>", html=True)
        self.assertContains(resp, "<li>条目一</li>", html=True)

    def test_view_count_increments(self):
        p = make_post()
        self.client.get(reverse("news:detail", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.view_count, 1)

    def test_level_gate_redirects_anonymous(self):
        p = make_post(min_level=Post.MinLevel.FORMAL)
        resp = self.client.get(reverse("news:detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_level_gate_forbids_low_level(self):
        p = make_post(min_level=Post.MinLevel.FORMAL)
        u = User.objects.create_user(username="low", password="Str0ngPass!2025", is_active=True)
        u.set_level(roles.LEVEL_APPLICANT)
        self.client.login(username="low", password="Str0ngPass!2025")
        resp = self.client.get(reverse("news:detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_unpublished_forbidden_for_member_visible_for_officer(self):
        p = make_post(is_published=False)
        resp = self.client.get(reverse("news:detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 403)

        officer = User.objects.create_user(username="off", password="Str0ngPass!2025", is_active=True)
        officer.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="off", password="Str0ngPass!2025")
        resp = self.client.get(reverse("news:detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)


class NewsDashboardTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="off", password="Str0ngPass!2025", is_active=True)
        self.officer.set_level(roles.LEVEL_OFFICER)

    def test_member_cannot_access_manage(self):
        u = User.objects.create_user(username="m", password="Str0ngPass!2025", is_active=True)
        u.set_level(roles.LEVEL_FORMAL)
        self.client.login(username="m", password="Str0ngPass!2025")
        resp = self.client.get(reverse("dashboard:news"))
        self.assertEqual(resp.status_code, 403)

    def test_manage_list_and_form_render(self):
        make_post(title="管理列表里的公告", author=self.officer)
        self.client.login(username="off", password="Str0ngPass!2025")
        resp = self.client.get(reverse("dashboard:news"))
        self.assertContains(resp, "管理列表里的公告")
        resp = self.client.get(reverse("dashboard:news_create"))
        self.assertContains(resp, "post-body")

    def test_officer_creates_post(self):
        self.client.login(username="off", password="Str0ngPass!2025")
        resp = self.client.post(reverse("dashboard:news_create"), {
            "title": "暑期培训通知",
            "category": "notice",
            "min_level": 0,
            "published_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "body": "# 大家好\n\n暑期培训开始报名。",
            "is_published": "on",
        })
        self.assertEqual(resp.status_code, 302)
        p = Post.objects.get(title="暑期培训通知")
        self.assertEqual(p.author, self.officer)

    def test_officer_toggle_publish_and_pin(self):
        p = make_post(author=self.officer)
        self.client.login(username="off", password="Str0ngPass!2025")
        self.client.post(reverse("dashboard:news"), {"id": p.pk, "action": "toggle_publish"})
        p.refresh_from_db()
        self.assertFalse(p.is_published)
        self.client.post(reverse("dashboard:news"), {"id": p.pk, "action": "pin"})
        p.refresh_from_db()
        self.assertTrue(p.pinned)

    def test_delete_requires_author_or_admin(self):
        other = User.objects.create_user(username="off2", password="Str0ngPass!2025", is_active=True)
        other.set_level(roles.LEVEL_OFFICER)
        p = make_post(author=self.officer)

        self.client.login(username="off2", password="Str0ngPass!2025")
        self.client.post(reverse("dashboard:news"), {"id": p.pk, "action": "delete"})
        self.assertTrue(Post.objects.filter(pk=p.pk).exists())

        self.client.login(username="off", password="Str0ngPass!2025")
        self.client.post(reverse("dashboard:news"), {"id": p.pk, "action": "delete"})
        self.assertFalse(Post.objects.filter(pk=p.pk).exists())

    def test_home_shows_latest_posts(self):
        make_post(title="首页应显示这条")
        resp = self.client.get(reverse("core:home"))
        self.assertContains(resp, "首页应显示这条")
