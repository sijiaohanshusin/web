from django.conf import settings
from django.db import models


class Notification(models.Model):
    """站内通知。业务模块统一通过 notify.services 写入，勿直接 create。"""

    class Kind(models.TextChoices):
        LEVEL = "level", "等级变更"
        MEDAL = "medal", "勋章授予"
        FEEDBACK = "feedback", "反馈动态"
        NEWS = "news", "公告"
        EVENT = "event", "活动"
        RECRUIT = "recruit", "招新"
        POINTS = "points", "积分"
        PROJECT = "project", "项目"
        SYSTEM = "system", "系统"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="接收人",
        on_delete=models.CASCADE, related_name="notifications",
    )
    kind = models.CharField("类型", max_length=12, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField("标题", max_length=120)
    body = models.CharField("内容", max_length=500, blank=True)
    url = models.CharField("跳转链接", max_length=300, blank=True, help_text="站内相对路径，点击通知后跳转")
    read_at = models.DateTimeField("已读时间", null=True, blank=True)
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        verbose_name = "站内通知"
        verbose_name_plural = "站内通知"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return f"→{self.user_id}「{self.title}」"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
