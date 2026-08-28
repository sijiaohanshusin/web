from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import roles

from .models import Project, ProjectFile, ProjectFolder, ProjectMember

User = get_user_model()


def make_user(name, level=roles.LEVEL_FORMAL):
    u = User.objects.create_user(username=name, password="Str0ngPass!2025", is_active=True)
    u.set_level(level)
    return u


def make_project(**kw):
    defaults = {"name": "示波器复刻", "department": Project.Department.HARDWARE}
    defaults.update(kw)
    return Project.objects.create(**defaults)


class ProjectAccessTests(TestCase):
    def setUp(self):
        self.project = make_project()
        self.lead = make_user("lead")
        self.outsider = make_user("outsider")
        ProjectMember.objects.create(project=self.project, user=self.lead, role=ProjectMember.Role.LEAD)

    def test_list_requires_member_level(self):
        pending = User.objects.create_user(username="p0", password="x", is_active=True)
        pending.set_level(roles.LEVEL_PENDING)
        self.client.force_login(pending)
        resp = self.client.get(reverse("projects:list"))
        self.assertEqual(resp.status_code, 403)

    def test_member_can_view_files_outsider_cannot(self):
        self.client.login(username="lead", password="Str0ngPass!2025")
        self.assertEqual(self.client.get(reverse("projects:detail", args=[self.project.pk])).status_code, 200)

        self.client.login(username="outsider", password="Str0ngPass!2025")
        self.assertEqual(self.client.get(reverse("projects:detail", args=[self.project.pk])).status_code, 403)

    def test_officer_sees_all_projects_files(self):
        officer = make_user("off", roles.LEVEL_OFFICER)
        self.client.login(username="off", password="Str0ngPass!2025")
        self.assertEqual(self.client.get(reverse("projects:detail", args=[self.project.pk])).status_code, 200)


class ProjectFileTests(TestCase):
    def setUp(self):
        self.project = make_project()
        self.lead = make_user("lead")
        self.outsider = make_user("outsider")
        ProjectMember.objects.create(project=self.project, user=self.lead, role=ProjectMember.Role.LEAD)
        self.client.login(username="lead", password="Str0ngPass!2025")

    def test_create_folder_and_nested(self):
        self.client.post(reverse("projects:create_folder", args=[self.project.pk]), {"name": "设计文档"})
        root_folder = ProjectFolder.objects.get(project=self.project, name="设计文档")
        self.assertIsNone(root_folder.parent)
        self.client.post(reverse("projects:create_folder", args=[self.project.pk]),
                         {"name": "原理图", "parent": root_folder.pk})
        child = ProjectFolder.objects.get(name="原理图")
        self.assertEqual(child.parent, root_folder)
        self.assertEqual([f.name for f in child.breadcrumb], ["设计文档", "原理图"])

    def test_duplicate_folder_rejected(self):
        self.client.post(reverse("projects:create_folder", args=[self.project.pk]), {"name": "文档"})
        self.client.post(reverse("projects:create_folder", args=[self.project.pk]), {"name": "文档"})
        self.assertEqual(ProjectFolder.objects.filter(project=self.project, name="文档").count(), 1)

    @override_settings(DEBUG=True)
    def test_upload_and_download(self):
        upload = SimpleUploadedFile("bom.csv", b"ref,qty\nR1,10\n", content_type="text/csv")
        self.client.post(reverse("projects:upload", args=[self.project.pk]), {"files": upload})
        pf = ProjectFile.objects.get(project=self.project)
        self.assertEqual(pf.name, "bom.csv")
        self.assertGreater(pf.size, 0)

        resp = self.client.get(reverse("projects:download", args=[self.project.pk, pf.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_upload(self):
        self.client.login(username="outsider", password="Str0ngPass!2025")
        upload = SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")
        resp = self.client.post(reverse("projects:upload", args=[self.project.pk]), {"files": upload})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(ProjectFile.objects.count(), 0)

    def test_delete_folder_cascades_files(self):
        self.client.post(reverse("projects:create_folder", args=[self.project.pk]), {"name": "临时"})
        folder = ProjectFolder.objects.get(name="临时")
        ProjectFile.objects.create(
            project=self.project, folder=folder,
            file=SimpleUploadedFile("a.txt", b"data"), uploader=self.lead,
        )
        self.client.post(reverse("projects:delete_folder", args=[self.project.pk, folder.pk]))
        self.assertFalse(ProjectFolder.objects.filter(pk=folder.pk).exists())
        self.assertEqual(ProjectFile.objects.filter(folder=folder).count(), 0)


class ProjectMemberMgmtTests(TestCase):
    def setUp(self):
        self.project = make_project()
        self.lead = make_user("lead")
        self.member = make_user("member")
        ProjectMember.objects.create(project=self.project, user=self.lead, role=ProjectMember.Role.LEAD)

    def test_lead_adds_member_by_username(self):
        self.client.login(username="lead", password="Str0ngPass!2025")
        self.client.post(reverse("projects:members", args=[self.project.pk]), {
            "action": "add", "username": "member", "role": "member",
        })
        self.assertTrue(ProjectMember.objects.filter(project=self.project, user=self.member).exists())

    def test_plain_member_cannot_manage(self):
        ProjectMember.objects.create(project=self.project, user=self.member, role=ProjectMember.Role.MEMBER)
        self.client.login(username="member", password="Str0ngPass!2025")
        resp = self.client.post(reverse("projects:members", args=[self.project.pk]), {
            "action": "add", "username": "lead", "role": "member",
        })
        self.assertEqual(resp.status_code, 403)


class ProjectDashboardTests(TestCase):
    def setUp(self):
        self.officer = make_user("off", roles.LEVEL_OFFICER)
        self.admin = make_user("adm", roles.LEVEL_ADMIN)
        self.client.login(username="off", password="Str0ngPass!2025")

    def test_officer_creates_project_with_lead(self):
        lead = make_user("newlead")
        resp = self.client.post(reverse("dashboard:project_create"), {
            "name": "电赛信号源", "department": "hardware", "summary": "复刻 AD9959 信号源", "status": "active",
            "lead": "newlead",
        })
        self.assertEqual(resp.status_code, 302)
        project = Project.objects.get(name="电赛信号源")
        self.assertTrue(ProjectMember.objects.filter(project=project, user=lead, role="lead").exists())

    def test_archive_and_activate(self):
        project = make_project()
        self.client.post(reverse("dashboard:projects"), {"id": project.pk, "action": "archive"})
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.ARCHIVED)

    def test_only_admin_deletes(self):
        project = make_project()
        # 干事无删除权
        self.client.post(reverse("dashboard:projects"), {"id": project.pk, "action": "delete"})
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())
        # 管理员可删除
        self.client.login(username="adm", password="Str0ngPass!2025")
        self.client.post(reverse("dashboard:projects"), {"id": project.pk, "action": "delete"})
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())


def make_cover(name="cover.png", size=(8, 6)):
    """一张真图。不要手写 base64 常量 —— `ImageField` 的表单校验会调 Pillow 的
    `verify()`，抄来的「1x1 PNG」CRC 常是坏的，能存进库但过不了表单。"""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, (13, 169, 205)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class WorksMediaPathTests(TestCase):
    """展示图必须落在 `works/` 下，不能落在 `projects/` 下。

    **这是本任务唯一一条会在线上炸、在本地完全看不出来的约束**：nginx 对
    `/media/projects/` 与 `/media/resources/` 直接返回 403（那里是会员私有文件，
    要经 `X-Accel-Redirect` 鉴权后才发），而开发环境用 Django 自己服务 media，
    放错路径一切正常。上线后就是一墙碎图。
    """

    def test_cover_uploads_outside_the_403ed_prefix(self):
        upload_to = Project._meta.get_field("cover").upload_to
        self.assertTrue(upload_to.startswith("works/"), upload_to)
        self.assertNotIn("projects/", upload_to)

    def test_shot_uploads_outside_the_403ed_prefix(self):
        from .models import ProjectShot

        upload_to = ProjectShot._meta.get_field("image").upload_to
        self.assertTrue(upload_to.startswith("works/"), upload_to)
        self.assertNotIn("projects/", upload_to)

    def test_private_project_files_still_live_under_projects(self):
        """反过来也要成立：私有文件必须留在被 403 的前缀下。"""
        from .models import project_file_path

        self.assertTrue(project_file_path(ProjectFile(project_id=7), "a.pdf")
                        .startswith("projects/"))


class ProjectPublicQuerysetTests(TestCase):
    """`Project.public()` 是「什么算公开」的唯一口径。

    三个消费者共用它：作品墙、作品详情页、首页精选。任何一处改用
    `Project.objects` 都会让外人看到还没准备好公开的东西 —— 而页面照常渲染。
    """

    def setUp(self):
        self.hidden = make_project(name="没公开的", is_public=False)
        self.plain = make_project(name="公开的", is_public=True)
        self.star = make_project(name="精选的", is_public=True, is_featured=True)

    def test_only_public_projects(self):
        self.assertNotIn(self.hidden, Project.public())
        self.assertIn(self.plain, Project.public())

    def test_featured_sorts_first(self):
        self.assertEqual(Project.public().first(), self.star)

    def test_projects_without_a_cover_are_not_hidden(self):
        """缺图是常态。把没封面的作品藏起来，等于让它永远不会被整理出来。"""
        self.assertFalse(self.plain.cover)
        self.assertIn(self.plain, Project.public())


class ProjectShowcaseFieldTests(TestCase):
    def test_tag_list_accepts_both_comma_shapes(self):
        """站务不会记得该用中文逗号还是英文逗号。"""
        p = make_project(tags="STM32，电赛, PCB ")
        self.assertEqual(p.tag_list, ["STM32", "电赛", "PCB"])

    def test_tag_list_is_empty_when_unset(self):
        self.assertEqual(make_project().tag_list, [])

    def test_teaser_prefers_highlight(self):
        p = make_project(highlight="量程自动切换", summary="很长的项目简介" * 20)
        self.assertEqual(p.teaser, "量程自动切换")

    def test_teaser_falls_back_to_a_trimmed_summary(self):
        p = make_project(summary="第一次任务，" * 30)
        self.assertLessEqual(len(p.teaser), 61)
        self.assertTrue(p.teaser.endswith("…"))


class WorksWallViewTests(TestCase):
    def setUp(self):
        self.hidden = make_project(name="没公开的东西", is_public=False,
                                   summary="还没整理好的内部内容")
        self.shown = make_project(name="公开的东西", is_public=True)

    def test_wall_is_open_to_anonymous_visitors(self):
        """作品墙是给还没加入的人看的，不能有登录门槛。"""
        resp = self.client.get(reverse("works:wall"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "公开的东西")

    def test_wall_does_not_leak_unpublished_projects(self):
        resp = self.client.get(reverse("works:wall"))
        self.assertNotContains(resp, "没公开的东西")
        self.assertNotContains(resp, "还没整理好的内部内容")

    def test_detail_404s_for_a_project_that_is_not_public(self):
        """光靠「不给链接」不算隐藏 —— id 是连续的，试第二个就中。"""
        resp = self.client.get(reverse("works:detail", args=[self.hidden.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_detail_renders_for_a_public_project(self):
        resp = self.client.get(reverse("works:detail", args=[self.shown.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "公开的东西")

    def test_archive_list_is_still_members_only(self):
        """回归：作品墙公开不代表档案库也公开了。"""
        resp = self.client.get(reverse("projects:list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_department_tabs_hide_empty_categories(self):
        """点进去一片空白的筛选项比没有这个筛选项更糟。"""
        resp = self.client.get(reverse("works:wall"))
        values = [v for v, _, _ in resp.context["dept_tabs"]]
        self.assertEqual(values, [Project.Department.HARDWARE])


class HomeFeaturedWorksTests(TestCase):
    """首页分镜 07。"""

    def test_section_absent_when_nothing_is_featured(self):
        """空壳区块比没有这一段更糟：它把「我们还什么都没有」摆在首页叙事位上。"""
        make_project(name="只是公开", is_public=True)
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.context["featured_works"], [])
        self.assertNotContains(resp, 'id="nf-works"')

    def test_featured_public_project_shows_with_a_link_to_the_wall(self):
        make_project(name="精选作品", is_public=True, is_featured=True)
        resp = self.client.get(reverse("core:home"))
        self.assertContains(resp, 'id="nf-works"')
        self.assertContains(resp, "精选作品")
        self.assertContains(resp, reverse("works:wall"))

    def test_featured_but_not_public_never_reaches_the_home_page(self):
        """否则首页会指向一个外人打开是 404 的页面。"""
        make_project(name="精选却没公开", is_public=False, is_featured=True)
        resp = self.client.get(reverse("core:home"))
        self.assertNotContains(resp, "精选却没公开")


class ProjectFormShowcaseTests(TestCase):
    def _payload(self, **over):
        data = {
            "name": "表单测试项目",
            "department": Project.Department.HARDWARE,
            "summary": "",
            "status": Project.Status.ACTIVE,
        }
        data.update(over)
        return data

    def test_featured_requires_public(self):
        from .forms import ProjectForm

        form = ProjectForm(self._payload(is_featured="on"))
        self.assertFalse(form.is_valid())
        self.assertIn("is_featured", form.errors)

    def test_featured_with_public_is_accepted(self):
        from .forms import ProjectForm

        form = ProjectForm(self._payload(is_public="on", is_featured="on"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_showcase_fields_are_grouped_separately_from_archive_fields(self):
        """模板按这两组分段渲染；合并成一坨会让「建项目」这件事看起来很重。"""
        from .forms import ProjectForm

        form = ProjectForm()
        archive = {f.name for f in form.archive_fields}
        showcase = {f.name for f in form.showcase_fields}
        self.assertEqual(archive & showcase, set())
        self.assertIn("cover", showcase)
        self.assertIn("name", archive)


class WorksCoverRenderTests(TestCase):
    """封面缺位时的渲染。"""

    def test_missing_cover_renders_the_empty_board_placeholder(self):
        p = make_project(name="没封面", is_public=True)
        resp = self.client.get(reverse("works:wall"))
        self.assertContains(resp, "slot is-empty")
        self.assertContains(resp, "slot-fid")
        self.assertContains(resp, "还差一张封面")
        # 绝不引一张不存在的图，也不换默认图糊过去
        self.assertNotContains(resp, "<img")
        self.assertEqual(p.tag_list, [])

    @override_settings(MEDIA_ROOT="/tmp/esta-test-media")
    def test_uploaded_cover_renders_an_image_under_works(self):
        p = make_project(name="有封面", is_public=True, cover=make_cover())
        resp = self.client.get(reverse("works:wall"))
        self.assertContains(resp, "wk-cover")
        self.assertIn("works/covers/", p.cover.name)
        # 真实像素尺寸要写进属性，避免图片落地时把下面的内容顶一下
        self.assertEqual((p.cover_w, p.cover_h), (8, 6))
