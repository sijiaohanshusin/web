from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from accounts.roles import effective_level

from .markdown import render_markdown


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True, published_at__lte=timezone.now())

    def visible_to(self, user):
        return self.filter(min_level__lte=effective_level(user))


class Post(models.Model):
    """公告/新闻。正文 Markdown，服务端渲染 + 消毒。"""

    class Category(models.TextChoices):
        NOTICE = "notice", "通知公告"
        ACTIVITY = "activity", "协会动态"
        HONOR = "honor", "获奖喜报"

    class MinLevel(models.IntegerChoices):
        PUBLIC = 0, "公开（所有人）"
        APPLICANT = 1, "报名会员及以上"
        PREPARATORY = 2, "预备会员及以上"
        FORMAL = 3, "正式会员及以上"
        OFFICER = 4, "干事及以上"

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
