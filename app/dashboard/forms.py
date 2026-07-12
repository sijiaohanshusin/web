from django import forms

from core.models import CarouselImage, SiteConfig


class SiteConfigForm(forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = ["site_name", "site_name_en", "founding_year", "recruit_video_bvid", "recruit_qq_group", "bilibili_mid"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()


class CarouselImageForm(forms.ModelForm):
    class Meta:
        model = CarouselImage
        fields = ["title", "caption", "image", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ("image", "is_active"):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()
