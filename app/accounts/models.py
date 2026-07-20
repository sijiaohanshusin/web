from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from . import roles


class Position(models.Model):
    """协会职位（主席、硬件主席、软件主席等），可在后台自定义增删。"""

    name = models.CharField("职位名称", max_length=30, unique=True)
    color = models.CharField("徽章颜色", max_length=20, default="#b8860b", help_text="十六进制色值，如 #b8860b")
    sort_order = models.PositiveIntegerField("排序", default=100, help_text="数字小的排前面")

    class Meta:
        verbose_name = "职位"
        verbose_name_plural = "职位"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """协会成员账号。member_level 为等级单一事实来源。"""

    real_name = models.CharField("姓名", max_length=30, blank=True)
    student_id = models.CharField("学号", max_length=20, blank=True, db_index=True)
    college = models.CharField("学院", max_length=50, blank=True)
    grade = models.CharField("年级", max_length=10, blank=True, help_text="入学年份，如 2025")
    qq = models.CharField("QQ 号", max_length=15, blank=True)
    phone = models.CharField("手机号", max_length=20, blank=True, db_index=True)
    avatar = models.ImageField("头像", upload_to="avatars/", blank=True)

    member_level = models.PositiveSmallIntegerField(
        "会员等级", choices=roles.LEVEL_CHOICES, default=roles.LEVEL_PENDING, db_index=True
    )
    position = models.ForeignKey(
        Position, verbose_name="职位", null=True, blank=True, on_delete=models.SET_NULL, related_name="holders"
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "成员"
        verbose_name_plural = "成员"

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.real_name or self.username

    @property
    def cohort_label(self) -> str:
        """届别标识：grade=2025 -> '25届'。无年级时返回空串。"""
        g = (self.grade or "").strip()
        if len(g) == 4 and g.isdigit():
            return f"{g[2:]}届"
        if g:
            return f"{g}届"
        return ""

    @property
    def level_label(self) -> str:
        return roles.LEVEL_LABELS.get(self.member_level, "待审核")

    @property
    def level_color(self) -> str:
        return roles.LEVEL_COLORS.get(self.member_level, "#97a1b3")

    @property
    def full_title(self) -> str:
        """全站统一展示：25届·正式会员（有职位时职位优先）。"""
        cohort = self.cohort_label
        base = self.position.name if self.position_id else self.level_label
        return f"{cohort}·{base}" if cohort else base

    @property
    def role_label(self) -> str:
        if self.is_superuser:
            return "超级管理员"
        return self.level_label

    @property
    def is_member(self) -> bool:
        return roles.is_member(self)

    @property
    def is_officer(self) -> bool:
        return roles.is_officer(self)

    @property
    def is_admin(self) -> bool:
        return roles.is_admin(self)

    def set_level(self, level: int, actor=None, note: str = "") -> None:
        """变更等级：写日志 + 同步激活状态与 Django 组 + 站内通知本人。"""
        old = self.member_level
        self.member_level = level
        if level >= roles.LEVEL_APPLICANT:
            self.is_active = True
        self.save(update_fields=["member_level", "is_active"])
        roles.sync_user_groups(self)
        if old != level:
            LevelLog.objects.create(
                user=self, from_level=old, to_level=level,
                operator=actor if getattr(actor, "pk", None) else None, note=note,
            )
            # 运行时导入，避免 notify ↔ accounts 启动期循环依赖
            from notify.models import Notification
            from notify.services import notify_user

            action = "晋升" if level > old else "调整"
            notify_user(
                self,
                f"你的会员等级已{action}为「{roles.LEVEL_LABELS.get(level, level)}」",
                kind=Notification.Kind.LEVEL,
                body=note or "",
                url="/accounts/profile/",
            )


class Medal(models.Model):
    """勋章/荣誉定义。管理员在后台创建，再授予成员。"""

    name = models.CharField("勋章名称", max_length=40, unique=True)
    icon = models.CharField("图标", max_length=40, default="🏅", help_text="直接填 emoji（推荐），如 🏅🥇⚡🔧")
    color = models.CharField("颜色", max_length=20, default="#c98a3d")
    description = models.CharField("说明", max_length=200, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=100)

    class Meta:
        verbose_name = "勋章"
        verbose_name_plural = "勋章"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class UserMedal(models.Model):
    """成员获得的勋章。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="成员", on_delete=models.CASCADE, related_name="medals")
    medal = models.ForeignKey(Medal, verbose_name="勋章", on_delete=models.CASCADE, related_name="awarded")
    reason = models.CharField("授予理由", max_length=200, blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="授予人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="medals_granted",
    )
    created_at = models.DateTimeField("授予时间", auto_now_add=True)

    class Meta:
        verbose_name = "成员勋章"
        verbose_name_plural = "成员勋章"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "medal"], name="uniq_user_medal")]

    def __str__(self):
        return f"{self.user} - {self.medal}"


class VerificationCode(models.Model):
    """邮箱验证码（注册 / 找回密码 / 验证码登录）。"""

    class Purpose(models.TextChoices):
        REGISTER = "register", "注册"
        RESET = "reset", "找回密码"
        LOGIN = "login", "验证码登录"

    email = models.EmailField("邮箱", db_index=True)
    code = models.CharField("验证码", max_length=6)
    purpose = models.CharField("用途", max_length=10, choices=Purpose.choices)
    attempts = models.PositiveSmallIntegerField("尝试次数", default=0)
    used = models.BooleanField("已使用", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "验证码"
        verbose_name_plural = "验证码"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "purpose", "used"])]

    def __str__(self):
        return f"{self.email} {self.get_purpose_display()} {self.code}"


class LevelLog(models.Model):
    """等级变更记录，用于换届追溯。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="成员", on_delete=models.CASCADE, related_name="level_logs")
    from_level = models.PositiveSmallIntegerField("原等级", choices=roles.LEVEL_CHOICES)
    to_level = models.PositiveSmallIntegerField("新等级", choices=roles.LEVEL_CHOICES)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="操作人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="level_ops",
    )
    note = models.CharField("备注", max_length=200, blank=True)
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        verbose_name = "等级变更记录"
        verbose_name_plural = "等级变更记录"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {roles.LEVEL_LABELS.get(self.from_level)}→{roles.LEVEL_LABELS.get(self.to_level)}"
