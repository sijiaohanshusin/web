from django.conf import settings
from django.core.cache import cache
from django.db import models

SITE_CONFIG_CACHE_KEY = "core:site_config"


class SiteConfig(models.Model):
    """全站配置（单例）。在 Admin 后台修改，改完立即生效，无需改代码。"""

    site_name = models.CharField("站点名称", max_length=50, default="哈尔滨工程大学电子科技协会")
    site_name_en = models.CharField("英文名称", max_length=100, default="HEU ESTA")
    founding_year = models.PositiveIntegerField("成立年份", default=1995)
    recruit_video_bvid = models.CharField(
        "招新视频 BV 号",
        max_length=20,
        default="BV1AhnGzVEsD",
        help_text="B 站视频的 BV 号，例如 BV1AhnGzVEsD。换招新视频时改这里即可。",
    )
    recruit_qq_group = models.CharField("招新 QQ 群号", max_length=20, default="1015304209")
    bilibili_mid = models.CharField("B 站账号 UID", max_length=20, default="70859324")

    beta_mode = models.BooleanField(
        "内测模式", default=True,
        help_text="开启后：全站显示内测反馈入口；新注册用户自动提升为干事以便测试全部功能。",
    )
    auto_approve = models.BooleanField(
        "注册自动审核", default=True,
        help_text="开启后：注册通过邮箱验证即自动激活，无需管理员手动审核。",
    )

    class Meta:
        verbose_name = "站点配置"
        verbose_name_plural = "站点配置"

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1  # 强制单例
        super().save(*args, **kwargs)
        cache.delete(SITE_CONFIG_CACHE_KEY)

    @property
    def bilibili_space_url(self):
        return f"https://space.bilibili.com/{self.bilibili_mid}"

    @classmethod
    def load(cls) -> "SiteConfig":
        config = cache.get(SITE_CONFIG_CACHE_KEY)
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(SITE_CONFIG_CACHE_KEY, config, 3600)
        return config


class Feedback(models.Model):
    """内测反馈：全站浮动按钮/独立页面提交，驾驶舱统一审阅处理。"""

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        RESOLVED = "resolved", "已处理"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="提交人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="feedbacks",
    )
    contact = models.CharField("联系方式", max_length=100, blank=True, help_text="QQ/邮箱，匿名提交时选填")
    page = models.CharField("提交页面", max_length=300, blank=True)
    content = models.TextField("反馈内容")
    status = models.CharField("状态", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    admin_note = models.CharField("处理备注", max_length=200, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="处理人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="feedbacks_resolved",
    )
    resolved_at = models.DateTimeField("处理时间", null=True, blank=True)
    created_at = models.DateTimeField("提交时间", auto_now_add=True)

    class Meta:
        verbose_name = "内测反馈"
        verbose_name_plural = "内测反馈"
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.content[:24]}"


class FeedbackReply(models.Model):
    """反馈下的回复：提交人与管理组可以往来对话。"""

    feedback = models.ForeignKey(Feedback, verbose_name="所属反馈", on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="回复人", null=True,
        on_delete=models.SET_NULL, related_name="feedback_replies",
    )
    content = models.TextField("内容")
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        verbose_name = "反馈回复"
        verbose_name_plural = "反馈回复"
        ordering = ["created_at"]

    def __str__(self):
        return f"回复#{self.pk} → 反馈#{self.feedback_id}"


class CarouselImage(models.Model):
    """首页轮播图。后台上传即可增删，排序值小的在前。"""

    title = models.CharField("标题", max_length=100)
    caption = models.CharField("说明文字", max_length=200, blank=True)
    image = models.ImageField("图片", upload_to="carousel/")
    sort_order = models.PositiveIntegerField("排序", default=100, help_text="数字小的排前面")
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "首页轮播图"
        verbose_name_plural = "首页轮播图"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title
