from django import forms

from .models import Honor, Post


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


class HonorForm(forms.ModelForm):
    """荣誉录入表单（驾驶舱 /dashboard/honors/ 用）。

    `post` 的候选只给**已发布的获奖喜报** —— 指向一篇没发布的喜报，荣誉墙上那个
    链接对外人就是 403（`news.views.post_detail` 会拦）。
    """

    class Meta:
        model = Honor
        fields = ("title", "contest", "level", "year", "awardee", "note",
                  "certificate", "post", "is_public", "is_featured")
        widgets = {
            "year": forms.NumberInput(attrs={"min": 1995, "max": 2100, "placeholder": "2025"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["post"].queryset = (
            Post.objects.published().filter(category=Post.Category.HONOR)
            .order_by("-published_at")
        )
        self.fields["post"].empty_label = "（不关联喜报）"
        for name, field in self.fields.items():
            # 勾选框和文件选择器有自己的外观，套 .input（文本框样式）会变形
            if isinstance(field.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()

    def clean_year(self):
        year = self.cleaned_data["year"]
        # 打错一位（205 / 20255）会让荣誉墙多出一个荒诞的年份分组，
        # 而清单本身看起来完全正常
        if not 1995 <= year <= 2100:
            raise forms.ValidationError("年份看着不对，应该在 1995 到 2100 之间。")
        return year

    def clean(self):
        cleaned = super().clean()
        # 首页展示必须先公开，否则首页列出一条外人看不到的记录
        if cleaned.get("is_featured") and not cleaned.get("is_public"):
            cleaned["is_featured"] = False
            self.add_error("is_featured", "要先勾「公开」才能放到首页。")
        return cleaned
