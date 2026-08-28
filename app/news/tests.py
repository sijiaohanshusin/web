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


# ============================================================
#  荣誉墙
# ============================================================

def make_honor(**kw):
    from .models import Honor

    defaults = {"title": "某个奖", "year": 2025, "level": Honor.Level.SCHOOL,
                "is_public": True}
    defaults.update(kw)
    return Honor.objects.create(**defaults)


def make_cert(name="cert.png", size=(8, 6)):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, (201, 138, 61)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class HonorMediaPathTests(TestCase):
    """证书照片不能落在被 nginx 403 的前缀下。

    和作品封面同一条约束：`/media/projects/` 与 `/media/resources/` 是会员私有
    文件的目录，nginx 直接 403。本地开发用 Django 服务 media，放错路径完全看不
    出来，上线才发现是一排碎图。
    """

    def test_certificate_uploads_outside_the_403ed_prefixes(self):
        from .models import Honor

        upload_to = Honor._meta.get_field("certificate").upload_to
        self.assertTrue(upload_to.startswith("honors/"), upload_to)
        for blocked in ("projects/", "resources/"):
            self.assertNotIn(blocked, upload_to)


class HonorModelTests(TestCase):
    def setUp(self):
        from .models import Honor

        self.Honor = Honor
        self.national = make_honor(title="电赛国一", level=Honor.Level.NATIONAL, year=2025)
        self.provincial = make_honor(title="省二", level=Honor.Level.PROVINCIAL, year=2025)
        self.school = make_honor(title="校三", level=Honor.Level.SCHOOL, year=2023)
        self.hidden = make_honor(title="待核实", level=Honor.Level.NATIONAL,
                                 year=2026, is_public=False)

    def test_wall_excludes_unpublished(self):
        titles = [h.title for h in self.Honor.wall()]
        self.assertNotIn("待核实", titles)
        self.assertEqual(len(titles), 3)

    def test_wall_sorts_by_year_then_level(self):
        """年份降序、同年按含金量降序。排序规则只在 Meta.ordering 一处。"""
        self.assertEqual(
            [(h.year, h.level) for h in self.Honor.wall()],
            [(2025, 30), (2025, 20), (2023, 10)],
        )

    def test_summary_counts_only_public_records(self):
        """「国家级 N 项」必须是数出来的 —— 手填的数字迟早和清单不一致。"""
        s = self.Honor.summary()
        self.assertEqual(s["national"], 1)     # 那条 2026 的没公开，不算
        self.assertEqual(s["provincial"], 1)
        self.assertEqual(s["school"], 1)
        self.assertEqual(s["total"], 3)

    def test_summary_year_range_ignores_unpublished(self):
        s = self.Honor.summary()
        self.assertEqual((s["year_from"], s["year_to"]), (2023, 2025))

    def test_summary_on_an_empty_wall(self):
        self.Honor.objects.all().delete()
        s = self.Honor.summary()
        self.assertEqual(s["total"], 0)
        self.assertIsNone(s["year_from"])

    def test_level_slug_is_ascii_for_css(self):
        """类名不能用 `get_level_display()` 拼 —— 那是中文，改一个字样式就没了。"""
        self.assertEqual(self.national.level_slug, "national")
        self.assertEqual(self.school.level_slug, "school")
        self.assertEqual(make_honor(level=self.Honor.Level.OTHER).level_slug, "other")

    def test_story_url_is_empty_without_a_post(self):
        self.assertEqual(self.national.story_url, "")

    def test_story_url_is_empty_when_the_post_is_unpublished(self):
        """指向一篇没发布的喜报，外人点进去是 403 —— 那就不该做成链接。"""
        draft = make_post(title="草稿喜报", category=Post.Category.HONOR, is_published=False)
        h = make_honor(post=draft)
        self.assertEqual(h.story_url, "")

    def test_story_url_points_at_a_published_post(self):
        live = make_post(title="正式喜报", category=Post.Category.HONOR)
        h = make_honor(post=live)
        self.assertEqual(h.story_url, live.get_absolute_url())


class HonorWallViewTests(TestCase):
    def setUp(self):
        from .models import Honor

        self.Honor = Honor
        make_honor(title="公开的奖", year=2025)
        make_honor(title="不公开的奖", year=2024, is_public=False,
                   note="内部备注不该泄漏")

    def test_wall_is_open_to_anonymous_visitors(self):
        resp = self.client.get(reverse("honors:wall"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "公开的奖")

    def test_wall_does_not_leak_unpublished_records(self):
        resp = self.client.get(reverse("honors:wall"))
        self.assertNotContains(resp, "不公开的奖")
        self.assertNotContains(resp, "内部备注不该泄漏")

    def test_years_are_grouped_without_duplicates(self):
        """分组是在 Python 里切段的（依赖 Meta.ordering 已排好），
        排序一变就会出现「2025 出现两次」。"""
        make_honor(title="同年第二个", year=2025, level=self.Honor.Level.NATIONAL)
        make_honor(title="更早的", year=2019)
        by_year = self.client.get(reverse("honors:wall")).context["by_year"]
        years = [y for y, _ in by_year]
        self.assertEqual(years, [2025, 2019])
        self.assertEqual(len(years), len(set(years)))
        self.assertEqual([len(items) for _, items in by_year], [2, 1])

    def test_certificate_strip_only_holds_records_that_have_one(self):
        """一张都没有时整段不渲染 —— 一排空占位框摆在这一页顶部最糟。"""
        resp = self.client.get(reverse("honors:wall"))
        self.assertEqual(resp.context["certificates"], [])
        self.assertNotContains(resp, "hn-cert-strip")

    def test_empty_wall_shows_a_designed_state_with_a_next_step(self):
        self.Honor.objects.all().delete()
        resp = self.client.get(reverse("honors:wall"))
        self.assertContains(resp, "empty-state")
        self.assertContains(resp, reverse("news:list"))


class HomeFeaturedHonorsTests(TestCase):
    def test_section_absent_when_nothing_is_featured(self):
        make_honor(title="只是公开")
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.context["featured_honors"], [])
        self.assertNotContains(resp, 'id="nf-honors"')

    def test_featured_public_honor_shows_with_a_link_to_the_wall(self):
        make_honor(title="首页那条", is_featured=True)
        resp = self.client.get(reverse("core:home"))
        self.assertContains(resp, 'id="nf-honors"')
        self.assertContains(resp, "首页那条")
        self.assertContains(resp, reverse("honors:wall"))

    def test_featured_but_not_public_never_reaches_the_home_page(self):
        make_honor(title="精选却没公开", is_public=False, is_featured=True)
        resp = self.client.get(reverse("core:home"))
        self.assertNotContains(resp, "精选却没公开")


class HonorFormTests(TestCase):
    def _payload(self, **over):
        from .models import Honor

        data = {"title": "某奖", "contest": "", "level": Honor.Level.SCHOOL,
                "year": 2025, "awardee": "", "note": ""}
        data.update(over)
        return data

    def test_year_typo_is_rejected(self):
        """打错一位会让荣誉墙多出一个荒诞的年份分组，而清单本身看起来完全正常。"""
        from .forms import HonorForm

        for bad in (205, 20255, 1800):
            with self.subTest(year=bad):
                form = HonorForm(self._payload(year=bad))
                self.assertFalse(form.is_valid())
                self.assertIn("year", form.errors)

    def test_featured_requires_public(self):
        from .forms import HonorForm

        form = HonorForm(self._payload(is_featured="on"))
        self.assertFalse(form.is_valid())
        self.assertIn("is_featured", form.errors)

    def test_post_choices_are_published_honor_posts_only(self):
        """候选里出现草稿或非喜报，站务就会关联出一个外人点不开的链接。"""
        from .forms import HonorForm

        live = make_post(title="已发布喜报", category=Post.Category.HONOR)
        make_post(title="草稿喜报", category=Post.Category.HONOR, is_published=False)
        make_post(title="普通通知", category=Post.Category.NOTICE)

        choices = list(HonorForm().fields["post"].queryset)
        self.assertEqual(choices, [live])


class HonorDashboardTests(TestCase):
    """站务是等级 4、没有 `is_staff`，打不开 Django Admin —— 所以这一页是刚需。"""

    def setUp(self):
        User = get_user_model()
        self.officer = User.objects.create_user(username="hoff", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.member = User.objects.create_user(username="hmem", password="x")
        self.member.set_level(roles.LEVEL_FORMAL)
        self.url = reverse("dashboard:honors")

    def test_officer_cannot_reach_django_admin(self):
        """这条是上面那句话的依据，不是废话：哪天 is_staff 的门槛变了，
        这一页可能就不再必要，而这条测试会先红。"""
        self.assertFalse(self.officer.is_staff)

    def test_plain_member_is_forbidden(self):
        self.client.login(username="hmem", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_officer_can_create(self):
        from .models import Honor

        self.client.login(username="hoff", password="x")
        resp = self.client.post(self.url, {
            "action": "save", "title": "站务录的奖", "level": Honor.Level.PROVINCIAL,
            "year": 2024, "contest": "", "awardee": "", "note": "", "is_public": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Honor.objects.filter(title="站务录的奖", year=2024).exists())

    def test_unpublishing_also_clears_the_home_page_flag(self):
        """否则首页会列出一条已经不公开的记录，点进去还在（墙上没有它了）。"""
        from .models import Honor

        h = make_honor(title="要撤回的", is_featured=True)
        self.client.login(username="hoff", password="x")
        self.client.post(self.url, {"action": "toggle_public", "id": h.pk})
        h.refresh_from_db()
        self.assertFalse(h.is_public)
        self.assertFalse(h.is_featured)

    def test_cannot_feature_a_record_that_is_not_public(self):
        h = make_honor(title="没公开的", is_public=False)
        self.client.login(username="hoff", password="x")
        self.client.post(self.url, {"action": "toggle_featured", "id": h.pk})
        h.refresh_from_db()
        self.assertFalse(h.is_featured)

    def test_dashboard_lists_unpublished_records_too(self):
        """驾驶舱要看得到全部 —— 不然站务不知道有哪些还没公开。"""
        make_honor(title="草稿记录", is_public=False)
        self.client.login(username="hoff", password="x")
        self.assertContains(self.client.get(self.url), "草稿记录")
