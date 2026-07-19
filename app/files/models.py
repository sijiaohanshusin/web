import os

from django.conf import settings
from django.db import models


class Resource(models.Model):
    """协会资料文件（培训课件、竞赛资料、工具软件等）。"""

    class Category(models.TextChoices):
        TRAINING = "training", "培训资料"
        CONTEST = "contest", "竞赛资料"
        TOOL = "tool", "工具软件"
        OTHER = "other", "其他"

    # 可见等级门槛：用户 member_level >= min_level 才能看到/下载
    class MinLevel(models.IntegerChoices):
        PUBLIC = 0, "公开（所有人）"
        APPLICANT = 1, "报名会员及以上"
        PREPARATORY = 2, "预备会员及以上"
        FORMAL = 3, "正式会员及以上"
        OFFICER = 4, "干事及以上"

    title = models.CharField("标题", max_length=200)
    description = models.TextField("说明", blank=True)
    category = models.CharField("分类", max_length=20, choices=Category.choices, default=Category.TRAINING)
    min_level = models.PositiveSmallIntegerField(
        "可见等级", choices=MinLevel.choices, default=MinLevel.PUBLIC,
        help_text="达到该等级的成员才能查看和下载",
    )
    file = models.FileField("文件", upload_to="resources/%Y/%m/")
    size = models.BigIntegerField("大小(字节)", default=0, editable=False)
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="上传者",
        null=True,
        on_delete=models.SET_NULL,
        related_name="resources",
    )
    download_count = models.PositiveIntegerField("下载次数", default=0, editable=False)
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "资料"
        verbose_name_plural = "资料"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, "size"):
            self.size = self.file.size
        super().save(*args, **kwargs)

    @property
    def filename(self) -> str:
        return os.path.basename(self.file.name)

    @property
    def extension(self) -> str:
        return os.path.splitext(self.file.name)[1].lstrip(".").upper() or "FILE"
