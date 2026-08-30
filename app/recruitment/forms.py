from django import forms
from django.contrib.auth import get_user_model

from accounts.forms import BIRTHDAY_FIELD, GENDER_FIELD

from .models import Application, Campaign

User = get_user_model()

# 勾了「其他」就必须写补充的那两对字段。(多选字段, 补充字段, 那一项的键)
#
# 放模块级：`class Meta` 的类体看不见外层类的类属性（Python 的类作用域不参与嵌套
# 查找），写成 ApplicationForm 的属性会在 Meta 里直接 NameError。
OTHER_PAIRS = (
    ("interests", "interests_other", Application.Interest.OTHER),
    ("heard_from", "heard_from_other", Application.Channel.OTHER),
)

# 不套 `.input` 的字段：单选卡片与多选组各有自己一套样式，`.input` 是**文本框**
# 的外观，套上去会让它们变成一个个奇怪的方框。
_NO_INPUT_CLASS = ("department", "interests", "heard_from")


class ApplicationForm(forms.ModelForm):
    """报名表。

    分步是**前端**的事：这里仍然是一张完整的表单，一次 POST 提交。模板把字段分到
    五个 fieldset 里，JS 一次只显示一个 —— 没有 JS 时五段全部展开，照样能填能交。
    分步做成多次请求会引入草稿存储、会话状态、回退处理一堆东西，而这张表的字段
    再多也就一屏多一点，不值得。

    这张表**只写 `Application`**。性别与出生日期属于账号档案（跨批次稳定，一个人
    报两次不该填两遍），由隔壁 `ApplicantProfileForm` 负责，两张表在同一个
    `<form>` 里、同一次 POST 提交 —— 见 `views.apply()`。
    """

    # 意向部门改成单选卡片：三个选项，卡片比下拉更适合「选方向」这种带图像感的决定，
    # 而且移动端不用弹系统选择器。
    department = forms.ChoiceField(
        label="想去哪个方向", choices=Application.Department.choices,
        widget=forms.RadioSelect, initial=Application.Department.UNDECIDED,
    )
    # 两项多选。**必填**，但都留了「不为难人」的出口：兴趣里有「目前还不了解」，
    # 渠道里有「其他」—— 所以没有人会被这两项卡住，而协会拿得到完整数据。
    #
    # 模型层是允许留空的（数据迁移与 admin 要能建半成品），「至少选一项」只在这一层。
    interests = forms.MultipleChoiceField(
        label="对什么感兴趣", choices=Application.Interest.choices,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "至少选一项。真的还没想法就选「目前还不了解」。"},
    )
    heard_from = forms.MultipleChoiceField(
        label="你是怎么知道我们的", choices=Application.Channel.choices,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "至少选一项 —— 这一项帮我们知道招新该往哪儿使劲。"},
    )

    class Meta:
        model = Application
        fields = (
            "department",
            "interests", "interests_other",
            "skills", "self_intro",
            "first_impression", "motto",
            "heard_from", "heard_from_other",
        )
        widgets = {
            "interests_other": forms.TextInput(attrs={"placeholder": "如：电机控制 / 机器视觉"}),
            "skills": forms.TextInput(attrs={"placeholder": "如：会一点 C 语言 / 焊过板子 / 零基础但很想学"}),
            # placeholder 和模型的 help_text **不能写同一句话** —— 那会在输入框里
            # 和框下面各印一遍，读起来像出了 bug。help_text 说「要写什么」，
            # placeholder 给一个具体的开头。
            "self_intro": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": "例：我在高中做过一个循迹小车，想学会自己画板子……",
            }),
            "first_impression": forms.Textarea(attrs={"rows": 3, "placeholder": "听说过什么、看过哪些作品、有什么好奇的（可不填）"}),
            "motto": forms.Textarea(attrs={"rows": 3, "placeholder": "想在大学四年里做成什么（可不填）"}),
            "heard_from_other": forms.TextInput(attrs={"placeholder": "如：在实验室门口看到的"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in _NO_INPUT_CLASS:
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()

    def clean_self_intro(self):
        text = (self.cleaned_data.get("self_intro") or "").strip()
        if len(text) < 10:
            raise forms.ValidationError("自我介绍太短了，多写几句让我们认识你（至少 10 个字）。")
        return text

    def clean(self):
        """勾了「其他」就得写补充，否则那一项等于什么都没说。

        错误挂在**补充字段**上而不是多选字段上 —— 那才是用户要动手的地方。挂错了
        的后果是提示出现在一排复选框下面，而光标该去的输入框旁边一片干净。
        """
        cleaned = super().clean()
        for multi, other, other_key in OTHER_PAIRS:
            picked = cleaned.get(multi) or []
            supplement = (cleaned.get(other) or "").strip()
            if other_key in picked and not supplement:
                self.add_error(other, "选了「其他」就请写一下具体是什么。")
            elif other_key not in picked and supplement:
                # 勾掉了却留着上次填的内容 —— 静默清掉，别把它存进库
                cleaned[other] = ""
        return cleaned


class ApplicantProfileForm(forms.ModelForm):
    """报名时顺带补齐的两项账号档案：性别与出生日期。

    **为什么单独一张表而不是塞进 ApplicationForm**：它们写的是 `User` 不是
    `Application`。一个 ModelForm 只能有一个 model，硬要一张表写两个模型就得自己
    接管 `save()`，那是把 Django 的校验链拆开重焊 —— 两张 ModelForm 各管一个模型、
    在视图里一起校验一起保存，是标准做法也短得多。

    字段定义复用 `accounts.forms` 的工厂：同样两个字段也出现在个人资料页上，
    各写一遍必然漂移（麻烦全在空选项标签与 date 输入框格式这些细节里）。
    """

    gender = GENDER_FIELD()
    birthday = BIRTHDAY_FIELD()

    class Meta:
        model = User
        fields = ("gender", "birthday")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ("name", "intro", "opens_at", "closes_at", "is_active")
        widgets = {
            "intro": forms.Textarea(attrs={"rows": 10, "id": "post-body"}),
            "opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("opens_at", "closes_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]
        for name, field in self.fields.items():
            if name != "is_active":
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()

    def clean(self):
        cleaned = super().clean()
        opens, closes = cleaned.get("opens_at"), cleaned.get("closes_at")
        if opens and closes and closes <= opens:
            self.add_error("closes_at", "截止时间必须晚于开放时间。")
        return cleaned
