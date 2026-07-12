from django.db import models


class BiliSnapshot(models.Model):
    """B 站数据每日快照（驾驶舱总览页自动落库），用于绘制粉丝增长曲线。"""

    date = models.DateField("日期", unique=True)
    follower = models.PositiveIntegerField("粉丝数", default=0)
    videos = models.PositiveIntegerField("视频数", default=0)
    likes = models.PositiveIntegerField("获赞数", default=0)

    class Meta:
        verbose_name = "B站数据快照"
        verbose_name_plural = "B站数据快照"
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} 粉丝 {self.follower}"
