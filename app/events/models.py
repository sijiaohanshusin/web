import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.roles import effective_level
from news.markdown import render_markdown

# 签到口令字符集：去掉易混淆的 0/O/1/I
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def make_checkin_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


class EventQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)

    def visible_to(self, user):
        return self.filter(min_level__lte=effective_level(user))


class Event(models.Model):
    """协会活动：培训、讲座、竞赛宣讲、例会等。"""

    class Kind(models.TextChoices):
        TRAINING = "training", "培训"
        LECTURE = "lecture", "讲座"
        CONTEST = "contest", "竞赛宣讲"
        MEETING = "meeting", "例会"
        OTHER = "other", "其他"

    class MinLevel(models.IntegerChoices):
        PUBLIC = 0, "公开（所有人）"
        APPLICANT = 1, "报名会员及以上"
        PREPARATORY = 2, "预备会员及以上"
        FORMAL = 3, "正式会员及以上"
        OFFICER = 4, "干事及以上"

    title = models.CharField("活动名称", max_length=120)
    kind = models.CharField("类型", max_length=12, choices=Kind.choices, default=Kind.TRAINING)
    description = models.TextField("活动详情（Markdown）", help_text="支持 Markdown：安排、要求、带什么东西等")
    location = models.CharField("地点", max_length=100, blank=True)
    start_at = models.DateTimeField("开始时间", db_index=True)
    end_at = models.DateTimeField("结束时间")
    signup_deadline = models.DateTimeField(
        "报名截止", null=True, blank=True,
        help_text="留空则报名到活动开始前一刻",
    )
    capacity = models.PositiveIntegerField("人数上限", default=0, help_text="0 表示不限")
    min_level = models.PositiveSmallIntegerField(
        "报名等级门槛", choices=MinLevel.choices, default=MinLevel.PUBLIC,
        help_text="达到该等级的成员才能看到并报名",
    )
    points_reward = models.PositiveSmallIntegerField("签到积分", default=5, help_text="成员签到成功后获得的积分，0 表示不给分")
    is_published = models.BooleanField("已发布", default=True)
    checkin_open = models.BooleanField("签到开放中", default=False, editable=False)
    checkin_code = models.CharField("签到口令", max_length=6, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="发布人", null=True,
        on_delete=models.SET_NULL, related_name="events_created",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        verbose_name = "活动"
        verbose_name_plural = "活动"
        ordering = ["-start_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:detail", args=[self.pk])

    @property
    def description_html(self) -> str:
        return render_markdown(self.description)

    @property
    def effective_deadline(self):
        return self.signup_deadline or self.start_at

    @property
    def is_finished(self) -> bool:
        return timezone.now() > self.end_at

    @property
    def is_ongoing(self) -> bool:
        return self.start_at <= timezone.now() <= self.end_at

    @property
    def signup_closed(self) -> bool:
        return timezone.now() > self.effective_deadline

    @property
    def status_label(self) -> str:
        if self.is_finished:
            return "已结束"
        if self.is_ongoing:
            return "进行中"
        if self.signup_closed:
            return "报名截止"
        return "报名中"

    def open_checkin(self) -> str:
        """开启签到并返回口令（重复开启沿用旧口令）。"""
        if not self.checkin_code:
            self.checkin_code = make_checkin_code()
        self.checkin_open = True
        self.save(update_fields=["checkin_open", "checkin_code"])
        return self.checkin_code

    def close_checkin(self) -> None:
        self.checkin_open = False
        self.save(update_fields=["checkin_open"])


class EventSignup(models.Model):
    """活动报名/签到记录。"""

    event = models.ForeignKey(Event, verbose_name="活动", on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="成员",
        on_delete=models.CASCADE, related_name="event_signups",
    )
    is_walkin = models.BooleanField("现场参加", default=False, help_text="未提前报名、现场签到时自动创建")
    checkin_at = models.DateTimeField("签到时间", null=True, blank=True)
    reminded = models.BooleanField("已发开场提醒", default=False, editable=False)
    created_at = models.DateTimeField("报名时间", auto_now_add=True)

    class Meta:
        verbose_name = "活动报名"
        verbose_name_plural = "活动报名"
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="uniq_event_signup")]

    def __str__(self):
        return f"{self.user} → {self.event}"

    @property
    def checked_in(self) -> bool:
        return self.checkin_at is not None
