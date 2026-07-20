from django import forms

from .models import Application, Campaign


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ("department", "skills", "self_intro")
        widgets = {
            "skills": forms.TextInput(attrs={"placeholder": "如：会一点 C 语言 / 焊过板子 / 零基础但很想学"}),
            "self_intro": forms.Textarea(attrs={"rows": 6, "placeholder": "简单介绍自己、为什么想加入、期待收获什么"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
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
