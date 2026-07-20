from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts import roles
from news.markdown import render_markdown


class Campaign(models.Model):
    """招新批次，如「2026 秋季招新」。同一时间通常只有一个进行中。"""

    name = models.CharField("批次名称", max_length=80)
    intro = models.TextField(
        "招新说明（Markdown）", blank=True,
        help_text="展示在报名页顶部：招新对象、流程、时间线、联系方式等",
    )
    opens_at = models.DateTimeField("开放报名时间", default=timezone.now)
    closes_at = models.DateTimeField("报名截止时间", null=True, blank=True, help_text="留空表示长期开放")
    is_active = models.BooleanField(
        "启用", default=True,
        help_text="仅启用且在时间窗内的批次会对外开放报名；同一时间建议只启用一个",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "招新批次"
        verbose_name_plural = "招新批次"
        ordering = ["-opens_at"]

    def __str__(self):
        return self.name

    @property
    def intro_html(self) -> str:
        return render_markdown(self.intro)

    @property
    def is_open(self) -> bool:
        """启用 + 已开放 + 未截止。"""
        now = timezone.now()
        if not self.is_active or self.opens_at > now:
            return False
        return self.closes_at is None or self.closes_at >= now

    @property
    def status_label(self) -> str:
        now = timezone.now()
        if not self.is_active:
            return "已停用"
        if self.opens_at > now:
            return "未开始"
        if self.closes_at and self.closes_at < now:
            return "已截止"
        return "报名中"


class Application(models.Model):
    """一名同学在某批次的报名 + 面试进展。"""

    class Department(models.TextChoices):
        HARDWARE = "hardware", "硬件部"
        SOFTWARE = "software", "软件部"
        UNDECIDED = "undecided", "都想试试 / 未定"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已报名"
        FIRST_PASS = "first_pass", "一面通过"
        SECOND_PASS = "second_pass", "二面通过"
        REJECTED = "rejected", "未录取"

    # 面试进展 -> 目标会员等级（用于批量晋级）
    STATUS_LEVEL = {
        Status.FIRST_PASS: roles.LEVEL_PREPARATORY,
        Status.SECOND_PASS: roles.LEVEL_FORMAL,
    }

    campaign = models.ForeignKey(
        Campaign, verbose_name="招新批次", on_delete=models.CASCADE, related_name="applications",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="报名人",
        on_delete=models.CASCADE, related_name="applications",
    )
    department = models.CharField(
        "意向部门", max_length=12, choices=Department.choices, default=Department.UNDECIDED,
    )
    skills = models.CharField("特长 / 已掌握技能", max_length=200, blank=True)
    self_intro = models.TextField("自我介绍", help_text="简单介绍自己、为什么想加入、期待收获什么")
    status = models.CharField(
        "进展", max_length=12, choices=Status.choices, default=Status.SUBMITTED, db_index=True,
    )
    interview_note = models.CharField("面试备注", max_length=300, blank=True, help_text="仅管理组可见")
    created_at = models.DateTimeField("报名时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "招新报名"
        verbose_name_plural = "招新报名"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "user"], name="uniq_campaign_application"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.campaign}"

    @property
    def status_color(self) -> str:
        return {
            self.Status.SUBMITTED: "#41d8e8",
            self.Status.FIRST_PASS: "#0da9cd",
            self.Status.SECOND_PASS: "#2568c8",
            self.Status.REJECTED: "#97a1b3",
        }.get(self.status, "#97a1b3")
