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
