from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from accounts.roles import content_level

from .markdown import render_markdown


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True, published_at__lte=timezone.now())

    def visible_to(self, user):
        return self.filter(min_level__lte=content_level(user))


class Post(models.Model):
    """公告/新闻。正文 Markdown，服务端渲染 + 消毒。"""

    class Category(models.TextChoices):
        NOTICE = "notice", "通知公告"
        ACTIVITY = "activity", "协会动态"
        HONOR = "honor", "获奖喜报"

    class MinLevel(models.IntegerChoices):
        PUBLIC = 0, "公开（所有人）"
        PREPARATORY = 2, "预备会员及以上"
        FORMAL = 3, "科协会员及以上"
        OFFICER = 4, "站务管理及以上"

    title = models.CharField("标题", max_length=120)
    category = models.CharField("栏目", max_length=12, choices=Category.choices, default=Category.NOTICE)
    cover = models.ImageField("封面图", upload_to="news/covers/%Y/", blank=True, help_text="选填，列表页与详情页顶部展示")
    body = models.TextField("正文（Markdown）", help_text="支持 Markdown：标题、加粗、列表、表格、图片、链接等")
    min_level = models.PositiveSmallIntegerField(
        "可见等级", choices=MinLevel.choices, default=MinLevel.PUBLIC,
        help_text="达到该等级的成员才能看到这篇公告",
    )
    pinned = models.BooleanField("置顶", default=False)
    is_published = models.BooleanField("已发布", default=True, help_text="取消勾选即下架（仅驾驶舱可见）")
    published_at = models.DateTimeField("发布时间", default=timezone.now, db_index=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="作者", null=True,
        on_delete=models.SET_NULL, related_name="news_posts",
    )
    view_count = models.PositiveIntegerField("浏览次数", default=0, editable=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = "公告"
        verbose_name_plural = "公告"
        ordering = ["-pinned", "-published_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("news:detail", args=[self.pk])

    @property
    def body_html(self) -> str:
        return render_markdown(self.body)

    @property
    def excerpt(self) -> str:
        """列表页摘要：渲染后剥标签，取前 120 字。"""
        text = strip_tags(self.body_html).strip()
        return text[:120] + ("…" if len(text) > 120 else "")


class HonorQuerySet(models.QuerySet):
    def public(self):
        return self.filter(is_public=True)


class Honor(models.Model):
    """一项获奖记录。荣誉墙（`/honors/`）的数据源。

    **为什么不复用 `Post` 的「获奖喜报」分类**：喜报是一篇 Markdown 文章，读起来
    是故事；荣誉墙要的是能排序、能按等级计数、能按年分组的**结构化字段**。用文章
    做墙，「国家级几项」只能靠人数，年份只能靠标题里的四个数字。

    两者不是替代关系而是互补：`post` 外键可以把一条记录指向它的那篇喜报，卡片
    就能深链到完整故事。

    证书照片是**可选的加分项，不是骨架**。荣誉墙的主体是排版密实的清单 ——
    二十张红底证书扫描件堆在一起像档案柜，而且协会现在一张都没有。有照片的那几
    项额外进顶部的「证书墙」条带，一张都没有时那条带整段不渲染。
    """

    class Level(models.IntegerChoices):
        """用数字而不是字符串：荣誉墙要按含金量从高到低排，字符串排不出来。"""

        NATIONAL = 30, "国家级"
        PROVINCIAL = 20, "省级"
        SCHOOL = 10, "校级"
        OTHER = 5, "其他"

    title = models.CharField("奖项", max_length=120, help_text="例如：全国大学生电子设计竞赛 一等奖")
    contest = models.CharField("赛事", max_length=80, blank=True, help_text="例如：电赛、蓝桥杯。留空则不显示")
    level = models.PositiveSmallIntegerField(
        "等级", choices=Level.choices, default=Level.SCHOOL, db_index=True,
    )
    year = models.PositiveSmallIntegerField("年份", db_index=True)
    awardee = models.CharField("获奖人 / 队伍", max_length=120, blank=True)
    note = models.CharField(
        "补充说明", max_length=200, blank=True,
        help_text="**会显示在公开页面上**，只写给访客看的话（届次、作品名、"
                  "指导教师、证书编号）。「这张照片是从哪来的、为什么没有证书图」"
                  "这类考证过程写进 docs/，不要写在这里 —— 这个字段不过 Markdown，"
                  "写了 ** 会原样印出来。",
    )
    certificate = models.ImageField(
        "证书照片", upload_to="honors/%Y/%m/", blank=True,
        width_field="cert_w", height_field="cert_h",
        help_text="选填。有照片的会额外出现在荣誉墙顶部的证书条带里。",
    )
    # width_field/height_field 必须可空：没有文件时 Django 会显式把它们设成 None
    cert_w = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cert_h = models.PositiveIntegerField(null=True, blank=True, editable=False)
    post = models.ForeignKey(
        Post, verbose_name="对应喜报", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="honors",
        help_text="选填。填了荣誉墙上这一项就能点进完整的喜报。",
    )
    is_public = models.BooleanField("公开", default=True, db_index=True)
    is_featured = models.BooleanField(
        "首页展示", default=False, help_text="首页只列几项。要先「公开」才有效。",
    )
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    objects = HonorQuerySet.as_manager()

    class Meta:
        verbose_name = "荣誉"
        verbose_name_plural = "荣誉"
        # 年份降序、同年按含金量降序：荣誉墙就是这个顺序，别在视图里再排一遍
        ordering = ["-year", "-level", "title"]

    def __str__(self):
        return f"{self.year} {self.title}"

    @property
    def level_slug(self) -> str:
        """给 CSS 用的等级标识（`hn-lv-national` 等）。

        不用 `get_level_display()` 拼类名 —— 那是中文，改一个字就把样式改没了。
        """
        return {
            self.Level.NATIONAL: "national",
            self.Level.PROVINCIAL: "provincial",
            self.Level.SCHOOL: "school",
        }.get(self.level, "other")

    @property
    def story_url(self) -> str:
        """对应喜报的地址，没有就返回空串（模板据此决定要不要做成链接）。"""
        if self.post_id and self.post.is_published:
            return self.post.get_absolute_url()
        return ""

    @classmethod
    def wall(cls):
        """荣誉墙 / 首页 08 共用的口径：只出公开的，排序走 Meta.ordering。"""
        return cls.objects.public().select_related("post")

    @classmethod
    def summary(cls) -> dict:
        """按等级计数 + 年份跨度，一次查询。

        「国家级 N 项」这种数字是这一页最有说服力的东西，所以它必须是**数出来的**
        而不是手填的 —— 手填的数字迟早和清单不一致。
        """
        rows = dict(cls.objects.public().values_list("level").annotate(n=models.Count("id")))
        years = cls.objects.public().aggregate(
            lo=models.Min("year"), hi=models.Max("year"),
        )
        return {
            "national": rows.get(cls.Level.NATIONAL, 0),
            "provincial": rows.get(cls.Level.PROVINCIAL, 0),
            "school": rows.get(cls.Level.SCHOOL, 0),
            "other": rows.get(cls.Level.OTHER, 0),
            "total": sum(rows.values()),
            "year_from": years["lo"],
            "year_to": years["hi"],
        }
