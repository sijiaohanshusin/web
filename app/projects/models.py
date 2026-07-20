import os

from django.conf import settings
from django.db import models
from django.urls import reverse


def project_file_path(instance, filename):
    return f"projects/{instance.project_id}/{filename}"


class Project(models.Model):
    """项目档案：一个课题/作品的资料归档空间，成员可读写、干事可见全部。"""

    class Department(models.TextChoices):
        HARDWARE = "hardware", "硬件部"
        SOFTWARE = "software", "软件部"
        JOINT = "joint", "软硬结合"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        ARCHIVED = "archived", "已归档"

    name = models.CharField("项目名称", max_length=120)
    summary = models.TextField("项目简介", blank=True)
    department = models.CharField("所属方向", max_length=12, choices=Department.choices, default=Department.OTHER)
    status = models.CharField("状态", max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="创建人", null=True,
        on_delete=models.SET_NULL, related_name="projects_created",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "项目"
        verbose_name_plural = "项目"
        ordering = ["status", "-updated_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])


class ProjectMember(models.Model):
    """项目成员及角色。负责人可管理成员与归档。"""

    class Role(models.TextChoices):
        LEAD = "lead", "负责人"
        MEMBER = "member", "成员"

    project = models.ForeignKey(Project, verbose_name="项目", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="成员", on_delete=models.CASCADE, related_name="project_memberships",
    )
    role = models.CharField("角色", max_length=8, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField("加入时间", auto_now_add=True)

    class Meta:
        verbose_name = "项目成员"
        verbose_name_plural = "项目成员"
        ordering = ["role", "joined_at"]
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="uniq_project_member")]

    def __str__(self):
        return f"{self.user} @ {self.project}（{self.get_role_display()}）"


class ProjectFolder(models.Model):
    """项目文件目录树的一个节点（parent 为空即项目根目录下的一级目录）。"""

    project = models.ForeignKey(Project, verbose_name="项目", on_delete=models.CASCADE, related_name="folders")
    parent = models.ForeignKey(
        "self", verbose_name="上级目录", null=True, blank=True,
        on_delete=models.CASCADE, related_name="children",
    )
    name = models.CharField("目录名", max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="创建人", null=True,
        on_delete=models.SET_NULL, related_name="project_folders_created",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "项目目录"
        verbose_name_plural = "项目目录"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "parent", "name"], name="uniq_folder_in_parent"),
        ]

    def __str__(self):
        return self.name

    @property
    def breadcrumb(self) -> list["ProjectFolder"]:
        """从根到当前的路径（含自己）。目录树一般很浅，直接向上走。"""
        chain, node = [], self
        while node is not None:
            chain.append(node)
            node = node.parent
        return list(reversed(chain))


class ProjectFile(models.Model):
    """项目内的一份文件，挂在某个目录（folder 为空即根目录）。"""

    project = models.ForeignKey(Project, verbose_name="项目", on_delete=models.CASCADE, related_name="files")
    folder = models.ForeignKey(
        ProjectFolder, verbose_name="所在目录", null=True, blank=True,
        on_delete=models.CASCADE, related_name="files",
    )
    name = models.CharField("显示名", max_length=200, blank=True)
    file = models.FileField("文件", upload_to=project_file_path)
    size = models.BigIntegerField("大小(字节)", default=0, editable=False)
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="上传者", null=True,
        on_delete=models.SET_NULL, related_name="project_files",
    )
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "项目文件"
        verbose_name_plural = "项目文件"
        ordering = ["name"]

    def __str__(self):
        return self.name or self.filename

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, "size"):
            self.size = self.file.size
        if not self.name and self.file:
            self.name = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    @property
    def filename(self) -> str:
        return os.path.basename(self.file.name)

    @property
    def extension(self) -> str:
        return os.path.splitext(self.file.name)[1].lstrip(".").upper() or "FILE"
