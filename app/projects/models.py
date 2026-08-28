import os

from django.conf import settings
from django.db import models
from django.urls import reverse


def project_file_path(instance, filename):
    return f"projects/{instance.project_id}/{filename}"


class Project(models.Model):
    """项目档案 + 对外作品展示，一个项目两副面孔。

    - **档案面**（`/projects/`）：成员的资料归档空间，文件树、可读写、只对会员开放。
    - **展示面**（`/works/`）：给外人看的作品墙，只出 `is_public=True` 的那些，
      内容是封面 + 图集 + 一句话亮点，不碰任何项目文件。

    做成一个模型而不是两个：一个项目就是一件事，拆成「项目」和「作品」两张表，
    迟早出现「作品墙上的那个和档案里的那个其实是同一个但数据对不上」。

    **展示用的图必须走 `works/` 而不是 `projects/`**：nginx 对 `/media/projects/`
    与 `/media/resources/` 直接返回 403（那里放的是会员私有文件，靠 X-Accel-Redirect
    鉴权后才发），公开封面放进去就是一片碎图，而且本地开发看不出来。
    """

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

    # ---------------- 对外展示（作品墙） ----------------
    is_public = models.BooleanField(
        "公开到作品墙", default=False, db_index=True,
        help_text="默认关闭。打开后这个项目会出现在 /works/ 上，外人可见。",
    )
    is_featured = models.BooleanField(
        "首页精选", default=False,
        help_text="首页只展示精选的几个。要先「公开到作品墙」才有效。",
    )
    highlight = models.CharField(
        "一句话亮点", max_length=120, blank=True,
        help_text="作品墙卡片上显示的一行字。留空则截取项目简介。",
    )
    tags = models.CharField(
        "标签", max_length=120, blank=True,
        help_text="逗号分隔，例如：STM32, 电赛, PCB。只用于展示，不参与筛选。",
    )
    cover = models.ImageField(
        "展示封面", upload_to="works/covers/%Y/%m/", blank=True,
        width_field="cover_w", height_field="cover_h",
        help_text="4:3 横构图。没有封面时作品墙显示空焊盘占位，不会是碎图。",
    )
    # width_field/height_field 必须可空：没有文件时 Django 会**显式**把它们设成
    # None（每次实例化都跑 update_dimension_fields），default=0 拦不住。
    cover_w = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_h = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "项目"
        verbose_name_plural = "项目"
        ordering = ["status", "-updated_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])

    # ---------------- 展示面 ----------------

    @classmethod
    def public(cls):
        """作品墙上该出现的项目，按「精选优先、然后最近更新」排。

        提到模型上是为了让三个消费者用同一个口径：作品墙、作品详情页、首页精选。
        散在各处迟早出现「首页显示了一个作品墙上没有的作品」。

        **不排除没有封面的**：缺图是常态，那种情况显示空焊盘占位（说明「这件作品
        还差一张照片」），比把整件作品藏起来诚实。
        """
        return (cls.objects.filter(is_public=True)
                .order_by("-is_featured", "-updated_at"))

    @property
    def tag_list(self) -> list[str]:
        """标签拆成列表。中英文逗号都认 —— 站务不会记得该用哪个。"""
        raw = (self.tags or "").replace("，", ",")
        return [t.strip() for t in raw.split(",") if t.strip()]

    @property
    def teaser(self) -> str:
        """卡片上那一行字：优先用亮点，没写就截简介。"""
        if self.highlight.strip():
            return self.highlight.strip()
        text = " ".join((self.summary or "").split())
        return text[:60] + ("…" if len(text) > 60 else "")

    @property
    def public_url(self) -> str:
        return reverse("works:detail", args=[self.pk])


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


class ProjectShot(models.Model):
    """作品的公开展示图（图集里的一张）。

    **和 `ProjectFile` 是两回事，别合并**：
    - `ProjectFile` 是会员私有的任意文件（原理图、代码、报告），路径在
      `projects/` 下，nginx 直接 403，只能经 `X-Accel-Redirect` 鉴权后取；
    - `ProjectShot` 是给外人看的照片，必须 nginx 直出，所以走 `works/shots/`。

    把展示图塞进 ProjectFile 会得到一个「本地开发好看、线上全是碎图」的作品墙。
    """

    project = models.ForeignKey(
        Project, verbose_name="项目", on_delete=models.CASCADE, related_name="shots",
    )
    image = models.ImageField(
        "展示图", upload_to="works/shots/%Y/%m/",
        width_field="width", height_field="height",
    )
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    caption = models.CharField("图注", max_length=120, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=100, help_text="数字小的排前面")
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "作品展示图"
        verbose_name_plural = "作品展示图"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.caption or f"{self.project} 的展示图 #{self.pk}"
