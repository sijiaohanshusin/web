from django import forms

from .models import Application, Campaign


class ApplicationForm(forms.ModelForm):
    """报名表。

    分步是**前端**的事：这里仍然是一张完整的表单，一次 POST 提交。模板把字段分到
    三个 fieldset 里，JS 一次只显示一个 —— 没有 JS 时三段全部展开，照样能填能交。
    分步做成多次请求会引入草稿存储、会话状态、回退处理一堆东西，而这张表只有三个
    字段，不值得。
    """

    # 意向部门改成单选卡片：三个选项，卡片比下拉更适合「选方向」这种带图像感的决定，
    # 而且移动端不用弹系统选择器。
    department = forms.ChoiceField(
        label="想去哪个方向", choices=Application.Department.choices,
        widget=forms.RadioSelect, initial=Application.Department.UNDECIDED,
    )

    class Meta:
        model = Application
        fields = ("department", "skills", "self_intro")
        widgets = {
            "skills": forms.TextInput(attrs={"placeholder": "如：会一点 C 语言 / 焊过板子 / 零基础但很想学"}),
            "self_intro": forms.Textarea(attrs={"rows": 6, "placeholder": "简单介绍自己、为什么想加入、期待收获什么"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            # 单选卡片自己有一套样式，不要套 .input（那是文本框的外观）
            if name == "department":
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()

    def clean_self_intro(self):
        text = (self.cleaned_data.get("self_intro") or "").strip()
        if len(text) < 10:
            raise forms.ValidationError("自我介绍太短了，多写几句让我们认识你（至少 10 个字）。")
        return text


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
