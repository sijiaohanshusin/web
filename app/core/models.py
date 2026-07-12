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
