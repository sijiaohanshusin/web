from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts import roles
from news.markdown import render_markdown


class Campaign(models.Model):
    """招新批次，如「2026 秋季招新」。同一时间通常只有一个进行中。"""

    name = models.CharField("批次名称", max_length=80)
    intro = models.TextField(
        "招新说明（Markdown）", blank=True,
        help_text="展示在报名页顶部：招新对象、流程、时间线、联系方式等",
    )
    opens_at = models.DateTimeField("开放报名时间", default=timezone.now)
    closes_at = models.DateTimeField("报名截止时间", null=True, blank=True, help_text="留空表示长期开放")
    is_active = models.BooleanField(
        "启用", default=True,
        help_text="仅启用且在时间窗内的批次会对外开放报名；同一时间建议只启用一个",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "招新批次"
        verbose_name_plural = "招新批次"
        ordering = ["-opens_at"]

    def __str__(self):
        return self.name

    @property
    def intro_html(self) -> str:
        return render_markdown(self.intro)

    @classmethod
    def current(cls) -> "Campaign | None":
        """对外展示用的「当前批次」：优先进行中的，否则最近一个启用的。

        放在模型上而不是某个视图里：报名页、导航条的招新入口、首页 CTA 的倒计时
        都要用同一个答案，散在各处迟早会出现「导航说在招新、首页说已截止」。
        """
        active = cls.objects.filter(is_active=True).order_by("-opens_at")
        for campaign in active:
            if campaign.is_open:
                return campaign
        return active.first()

    @property
    def is_open(self) -> bool:
        """启用 + 已开放 + 未截止。"""
        now = timezone.now()
        if not self.is_active or self.opens_at > now:
            return False
        return self.closes_at is None or self.closes_at >= now

    @property
    def status_label(self) -> str:
        now = timezone.now()
        if not self.is_active:
            return "已停用"
        if self.opens_at > now:
            return "未开始"
        if self.closes_at and self.closes_at < now:
            return "已截止"
        return "报名中"


class Application(models.Model):
    """一名同学在某批次的报名 + 面试进展。"""

    class Department(models.TextChoices):
        HARDWARE = "hardware", "硬件部"
        SOFTWARE = "software", "软件部"
        UNDECIDED = "undecided", "都想试试 / 未定"

    # 感兴趣的技术方向（多选）。照纸质《会员申请表》上那八项抄的，另加「其他」。
    #
    # 和 `Department` 是**两件事，刻意并存**：部门 = 你进哪个组（招新分配用），
    # 方向 = 你对什么感兴趣（培训排课用）。一个人可以进硬件部同时对 FPGA 感兴趣。
    class Interest(models.TextChoices):
        RF = "rf", "高频 / 射频无线"
        MCU = "mcu", "单片机编程与设计"
        EMBEDDED = "embedded", "嵌入式与上位机开发"
        ANALOG = "analog", "模拟电子系统设计"
        DSP_FPGA = "dsp_fpga", "DSP / FPGA 应用设计"
        POWER = "power", "电源开发与设计"
        MODEL = "model", "模型控制类"
        UNKNOWN = "unknown", "目前还不了解"
        OTHER = "other", "其他"

    # 从哪儿知道我们的（多选）。这一项是**给协会的反馈**，不是关于申请人的 ——
    # 它的用途是评估招新方式的效果，所以在报名表里排在最后。
    #
    # 纸质表上写的是「海报/网站/QQ/人人等」和「信通科协招新活动」，这里按现状改了
    # 两处字面：人人网早没了，换成公众号；站上的名字是电子科技协会，不写「信通科协」。
    class Channel(models.TextChoices):
        CAMPAIGN = "campaign", "协会招新活动"
        MENTOR = "mentor", "名誉寝室长 / 科创导航员 / 心灵导航员推荐"
        SENIOR = "senior", "高年级学长学姐介绍"
        SCHOOL = "school", "学校 / 学院 / 辅导员介绍"
        ONLINE = "online", "海报 / 官网 / QQ / 公众号"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已报名"
        FIRST_PASS = "first_pass", "一面通过"
        SECOND_PASS = "second_pass", "二面通过"
        REJECTED = "rejected", "未录取"

    # 面试进展 -> 目标会员等级（用于批量晋级）
    STATUS_LEVEL = {
        Status.FIRST_PASS: roles.LEVEL_PREPARATORY,
        Status.SECOND_PASS: roles.LEVEL_FORMAL,
    }

    # 报名进度时间线的节点。(键, 标题, 说明)
    #
    # 只有三个节点，「未录取」不在其中 —— 它不是流程上的第四步，而是任何一步都
    # 可能走到的**终止态**。把它排进时间线会变成「未录取是最后一个成就」，既别扭
    # 也不准确。模板里单独渲染。
    PROGRESS_STEPS = (
        ("submitted", "已报名", "材料收到了，等面试安排"),
        ("first_pass", "一面通过", "成为预备会员，解锁会员内容"),
        ("second_pass", "二面通过", "成为科协会员，正式入队"),
    )

    @property
    def reached_index(self) -> int:
        """当前进展走到了 PROGRESS_STEPS 的第几个（0 起）。未录取按走到过的最远处算。"""
        order = [key for key, _, _ in self.PROGRESS_STEPS]
        if self.status == self.Status.REJECTED:
            # 未录取时数据库里不再保留「之前通过到哪一面」，只能确定报名这一步成立
            return 0
        return order.index(self.status) if self.status in order else 0

    @property
    def is_rejected(self) -> bool:
        return self.status == self.Status.REJECTED

    campaign = models.ForeignKey(
        Campaign, verbose_name="招新批次", on_delete=models.CASCADE, related_name="applications",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="报名人",
        on_delete=models.CASCADE, related_name="applications",
    )
    department = models.CharField(
        "意向部门", max_length=12, choices=Department.choices, default=Department.UNDECIDED,
    )
    # ---- 多选两项：存 JSONField 里的键数组 ----
    #
    # **为什么不建查表**：这些选项是纸质申请表上印死的，不该让人在后台改 —— 改了
    # 历史数据的含义就漂了（去年的「其他」和今年的「其他」不是一件事）。`TextChoices`
    # 让选项集合是代码里的单一事实来源，动它要过 code review + 迁移。
    #
    # **代价要记住：`JSONField` 对内容零校验**，往里塞任何 JSON 都能存进去，而
    # `clean()` 在 `save()` 时压根不跑。所以这一层靠三样东西一起兜：
    #   1. 表单用 `MultipleChoiceField`，非法键在那里就被拒（正常入口）
    #   2. 下面的 `clean()`（`full_clean()` 时生效，admin 走这条）
    #   3. `*_labels` 显示时**静默跳过认不出的键** —— 以后退役一个选项，
    #      历史数据不会因此炸页面
    # 三条都有测试钉着。
    #
    # 模型层允许留空（数据迁移与 admin 要能建半成品），**「至少选一项」是表单层的
    # 要求** —— 两层的职责不同，别把它写进模型。
    interests = models.JSONField(
        "感兴趣的方向", default=list, blank=True,
        help_text="Interest 的键数组。多选，允许含 other（补充写在 interests_other）",
    )
    interests_other = models.CharField("其他方向", max_length=60, blank=True)
    skills = models.CharField(
        "主要经历（电子方面）/ 兴趣爱好", max_length=200, blank=True,
        help_text="做过什么、玩过什么。零基础就写零基础，这一项不筛人",
    )
    self_intro = models.TextField("自我介绍", help_text="简单介绍自己、为什么想加入、期待收获什么")
    first_impression = models.TextField("对协会的初步印象", blank=True)
    motto = models.TextField("对大学四年的寄语", blank=True)
    heard_from = models.JSONField(
        "从哪儿知道我们的", default=list, blank=True,
        help_text="Channel 的键数组。多选，允许含 other（补充写在 heard_from_other）",
    )
    heard_from_other = models.CharField("其他渠道", max_length=60, blank=True)
    status = models.CharField(
        "进展", max_length=12, choices=Status.choices, default=Status.SUBMITTED, db_index=True,
    )
    interview_note = models.CharField("面试备注", max_length=300, blank=True, help_text="仅管理组可见")
    created_at = models.DateTimeField("报名时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "招新报名"
        verbose_name_plural = "招新报名"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "user"], name="uniq_campaign_application"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.campaign}"

    @property
    def status_color(self) -> str:
        return {
            self.Status.SUBMITTED: "#41d8e8",
            self.Status.FIRST_PASS: "#0da9cd",
            self.Status.SECOND_PASS: "#2568c8",
            self.Status.REJECTED: "#97a1b3",
        }.get(self.status, "#97a1b3")

    # ------------------------------------------------------------ 多选两项的读写
    #
    # 这一段是 `interests` / `heard_from` 的唯一出口。驾驶舱详情页、CSV 导出、
    # 分布统计都从这里取 —— 别在模板或视图里再拆一遍键数组，那就是第二份实现。

    MULTI_CHOICE_FIELDS = {
        "interests": ("Interest", "interests_other"),
        "heard_from": ("Channel", "heard_from_other"),
    }

    @staticmethod
    def _multi_display(keys, choices, other_key, other_text: str) -> str:
        """键数组 → 一行中文。选了「其他」且写了补充就接在后面。

        **认不出的键静默跳过。** 选项以后可能退役（纸质表上原来还有「人人网」），
        而历史数据里仍留着旧键：原样显示会在页面上冒出一个 `rr_net`，抛异常会让
        整页 500 —— 跳过是唯一不制造新问题的选择。这条有测试钉着。
        """
        labels = dict(choices)
        out = []
        for key in keys or []:
            if key not in labels:
                continue
            if key == other_key and other_text:
                out.append(f"{labels[key]}：{other_text}")
            else:
                out.append(labels[key])
        return "、".join(out)

    @property
    def interests_display(self) -> str:
        return self._multi_display(self.interests, self.Interest.choices,
                                   self.Interest.OTHER, self.interests_other)

    @property
    def channels_display(self) -> str:
        return self._multi_display(self.heard_from, self.Channel.choices,
                                   self.Channel.OTHER, self.heard_from_other)

    def clean(self):
        """挡住不在 choices 里的键。

        **注意 `clean()` 在 `save()` 时不跑** —— 只有 `full_clean()`（表单与 admin
        会调）才走这里。所以正常入口靠表单的 `MultipleChoiceField` 挡，这一层是
        给 admin 和直接调 `full_clean()` 的地方兜底；而通过 ORM 硬塞进来的脏数据
        由 `_multi_display` 的「跳过认不出的键」保证不会炸页面。三层各管一段。
        """
        super().clean()
        errors = {}
        for field, (choices_name, _) in self.MULTI_CHOICE_FIELDS.items():
            value = getattr(self, field)
            if value in (None, ""):
                continue
            if not isinstance(value, list):
                errors[field] = "必须是一个数组。"
                continue
            valid = set(getattr(self, choices_name).values)
            bad = [str(k) for k in value if k not in valid]
            if bad:
                errors[field] = f"不认识的选项：{'、'.join(bad)}"
        if errors:
            raise ValidationError(errors)

    @staticmethod
    def _breakdown(applications, field: str, choices) -> list[tuple[str, int]]:
        """按固定选项顺序数每一项被选了多少次，返回 [(中文标签, 次数), ...]。

        在 Python 里数而不是发查询：`JSONField` 要按项统计就得每个选项一条
        `contains` 查询（六到九条），而调用方本来就已经把这一批报名取回内存了
        （驾驶舱那一页要逐行渲染）。多一次遍历比多九次往返便宜得多。

        **返回全部选项，包括 0 次的** —— 「一个人都没选电源方向」本身就是要看的
        信息，只返回非零项会让那一行凭空消失、读者以为漏统计了。
        """
        counts: dict[str, int] = {}
        for application in applications:
            for key in getattr(application, field) or []:
                counts[key] = counts.get(key, 0) + 1
        return [(label, counts.get(value, 0)) for value, label in choices]

    @classmethod
    def interest_breakdown(cls, applications) -> list[tuple[str, int]]:
        return cls._breakdown(applications, "interests", cls.Interest.choices)

    @classmethod
    def channel_breakdown(cls, applications) -> list[tuple[str, int]]:
        return cls._breakdown(applications, "heard_from", cls.Channel.choices)
