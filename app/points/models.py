from django.conf import settings
from django.db import models


class PointLog(models.Model):
    """积分流水（唯一事实来源，总分 = SUM(delta)）。统一走 points.services 写入。"""

    class Source(models.TextChoices):
        EVENT_CHECKIN = "event", "活动签到"
        ADMIN_ADJUST = "admin", "管理调整"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="成员",
        on_delete=models.CASCADE, related_name="point_logs",
    )
    delta = models.IntegerField("分值变化", help_text="正数加分，负数扣分")
    source = models.CharField("来源", max_length=10, choices=Source.choices)
    note = models.CharField("说明", max_length=200, blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="操作人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="point_ops",
        help_text="手动调整时的操作人；系统发放为空",
    )
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        verbose_name = "积分流水"
        verbose_name_plural = "积分流水"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.user} {sign}{self.delta}（{self.get_source_display()}）"
