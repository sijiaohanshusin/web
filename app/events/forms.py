from django import forms

from .models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "title", "kind", "location", "start_at", "end_at", "signup_deadline",
            "capacity", "min_level", "points_reward", "is_published", "description",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 12, "id": "post-body"}),
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "signup_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("start_at", "end_at", "signup_deadline"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]
        for name, field in self.fields.items():
            if name != "is_published":
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_at"), cleaned.get("end_at")
        deadline = cleaned.get("signup_deadline")
        if start and end and end <= start:
            self.add_error("end_at", "结束时间必须晚于开始时间。")
        if start and deadline and deadline > start:
            self.add_error("signup_deadline", "报名截止不能晚于活动开始。")
        return cleaned
