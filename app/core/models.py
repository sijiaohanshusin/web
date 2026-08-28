import re

from django.conf import settings
from django.core.cache import cache
from django.db import models

# 加字段后 bump 版本号，避免部署后读到缺新字段的旧 pickle
SITE_CONFIG_CACHE_KEY = "core:site_config:v3"
# 同上：MediaSlot 加字段也要 bump。生产是 DatabaseCache，缓存的是 pickle 实例
MEDIA_SLOT_CACHE_KEY = "core:media_slots:v2"


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
    recruit_qq_group = models.CharField("招新 QQ 群号", max_length=20, default="1081376858")
    bilibili_mid = models.CharField("B 站账号 UID", max_length=20, default="70859324")
    featured_video_bvids = models.TextField(
        "首页精选视频 BV 号",
        blank=True,
        default="",
        help_text="每行一个 BV 号，最多取前 3 个，作为首页「精选培训视频」展示；"
                  "留空则自动展示最新 3 个投稿。挑封面干净的视频放这里。",
    )

    beta_mode = models.BooleanField(
        "内测模式（已停用）", default=False, editable=False,
        help_text="正式招新版本不再使用此开关。",
    )
    auto_approve = models.BooleanField(
        "旧版自动审核（已停用）", default=False, editable=False,
        help_text="正式版本改用新会员自动激活、老会员单独审核。",
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

    @property
    def featured_bvid_list(self) -> list[str]:
        """解析精选视频 BV 号（每行一个，容忍逗号/空格分隔），最多 3 个。"""
        bvids = re.split(r"[\s,，]+", self.featured_video_bvids.strip())
        return [b for b in bvids if b][:3]

    @classmethod
    def load(cls) -> "SiteConfig":
        config = cache.get(SITE_CONFIG_CACHE_KEY)
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(SITE_CONFIG_CACHE_KEY, config, 3600)
        return config


class Feedback(models.Model):
    """网站问题反馈：独立页面提交，驾驶舱统一审阅处理。"""

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
        verbose_name = "网站问题反馈"
        verbose_name_plural = "网站问题反馈"
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


class MediaSlot(models.Model):
    """一个素材槽里实际填进去的图。

    槽位本身**不在这张表里**，而是在 `core/slots.py` 的登记表里声明（那边有
    为什么这么分工的完整说明）。这张表只回答「那个位置现在放的是哪张图」。
    所以没有对应行的槽位不是错误状态，是「还没拍」，页面会渲染成设计过的
    占位框。

    key 与登记表对不上时不会静默：`SlotRegistryTests` 扫描全部模板做比对。
    """

    key = models.CharField(
        "槽位标识", max_length=80, unique=True,
        help_text="必须与 core/slots.py 登记表里的 key 完全一致",
    )
    image = models.ImageField(
        "图片", upload_to="slots/%Y/%m/",
        width_field="width", height_field="height",
    )
    # 存下真实像素尺寸，模板才能写出 width/height 属性。少了它，图片加载完成
    # 的那一刻会把下面的内容顶一下（CLS），一屏十几张图就是十几次跳动。
    #
    # 必须 null=True，不能用 default=0：Django 的 update_dimension_fields 在
    # 没有文件时会**显式**把这两个字段设成 None（每次实例化都会跑一遍），
    # default 拦不住，插入时直接 NOT NULL 约束失败。这是 ImageField 的
    # width_field/height_field 的既定行为，官方示例也是可空的。
    width = models.PositiveIntegerField("宽", null=True, blank=True, editable=False)
    height = models.PositiveIntegerField("高", null=True, blank=True, editable=False)

    # 视频槽：image 字段身份变成「封面帧」，这两个是可选的循环片段。
    # 两种格式都传是为了覆盖面：H.264 mp4 到处都能放，VP9 webm 同画质小三成。
    # 只传封面也完全可用 —— 那就退化成一张静态图，不需要另备降级素材。
    video_mp4 = models.FileField(
        "循环片段 MP4", upload_to="slots/video/%Y/%m/", blank=True,
        help_text="H.264 / 720p / 无声。单文件建议不超过 1.5MB。",
    )
    video_webm = models.FileField(
        "循环片段 WebM", upload_to="slots/video/%Y/%m/", blank=True,
        help_text="VP9，同画质比 MP4 小三成左右。可以不传。",
    )

    alt = models.CharField(
        "替代文本", max_length=200, blank=True,
        help_text="给读屏软件描述画面内容。留空则用登记表里的名字，但那通常不够具体。",
    )
    caption = models.CharField("图注", max_length=200, blank=True)
    credit = models.CharField("拍摄者", max_length=60, blank=True)

    # 走廊、卡片都是定比例裁切，主体不在正中就会被切掉头。这两个值直接喂给
    # CSS 的 object-position，站务不必自己去裁图。
    focal_x = models.PositiveSmallIntegerField("焦点横向 %", default=50)
    focal_y = models.PositiveSmallIntegerField("焦点纵向 %", default=50)

    is_active = models.BooleanField(
        "启用", default=True,
        help_text="取消勾选后该位置回到占位状态，图片本身保留",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="最后修改人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="media_slots_updated",
    )
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "素材槽"
        verbose_name_plural = "素材槽"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(MEDIA_SLOT_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(MEDIA_SLOT_CACHE_KEY)

    @property
    def object_position(self) -> str:
        return f"{self.focal_x}% {self.focal_y}%"

    @property
    def video_sources(self) -> list[tuple[str, str]]:
        """(url, mime) 列表，webm 排前面让支持它的浏览器优先选到更小的那份。"""
        out = []
        if self.video_webm:
            out.append((self.video_webm.url, "video/webm"))
        if self.video_mp4:
            out.append((self.video_mp4.url, "video/mp4"))
        return out

    @property
    def has_video(self) -> bool:
        return bool(self.video_webm or self.video_mp4)

    @classmethod
    def load_all(cls) -> dict[str, "MediaSlot"]:
        """一次取回所有启用的槽位内容，按 key 索引。

        `{% slot %}` 每次调用都查一次库的话，一个首页就是十几次查询。素材
        变动极少，所以整张表缓存起来，写入时删键。
        """
        slots = cache.get(MEDIA_SLOT_CACHE_KEY)
        if slots is None:
            slots = {obj.key: obj for obj in cls.objects.filter(is_active=True)}
            cache.set(MEDIA_SLOT_CACHE_KEY, slots, 3600)
        return slots


class CarouselImage(models.Model):
    """首页轮播图。

    **已被素材槽（MediaSlot + core/slots.py）取代，不再驱动首页图片走廊。**
    保留模型与数据是为了不丢已上传的图；等 Task 10/11 重做首页、站务把图搬到
    素材中心之后再删。新增展示位不要再用这张表。
    """

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
