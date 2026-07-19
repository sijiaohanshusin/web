from django import forms

from .models import Resource


class ResourceUploadForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ("title", "description", "category", "min_level", "file")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "file":
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()
