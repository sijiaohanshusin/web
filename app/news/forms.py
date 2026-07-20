from django import forms

from .models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("title", "category", "cover", "min_level", "pinned", "is_published", "published_at", "body")
        widgets = {
            "body": forms.Textarea(attrs={"rows": 16, "id": "post-body"}),
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        for name, field in self.fields.items():
            if name not in ("cover", "pinned", "is_published"):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()
