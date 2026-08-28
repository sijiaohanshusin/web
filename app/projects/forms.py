from django import forms

from .models import Project

# 放模块级而不是类属性：`class Meta` 的类体看不见外层类的命名空间
# （Python 的类作用域不参与嵌套查找），写成 ProjectForm.ARCHIVE_FIELDS 会 NameError。
ARCHIVE_FIELDS = ("name", "department", "summary", "status")
SHOWCASE_FIELDS = ("is_public", "is_featured", "highlight", "tags", "cover")


class ProjectForm(forms.ModelForm):
    """驾驶舱里的项目表单：档案信息 + 对外展示设置。

    展示那几项排在后面并单独成组（模板按 `showcase_fields` 分段）—— 建项目时
    多数人只填前四项，展示是作品做完之后才有的事。
    """

    class Meta:
        model = Project
        fields = ARCHIVE_FIELDS + SHOWCASE_FIELDS
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            # 勾选框和文件选择器有自己的外观，套 .input（文本框样式）会变形
            if isinstance(field.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()

    @property
    def archive_fields(self):
        return [self[name] for name in ARCHIVE_FIELDS]

    @property
    def showcase_fields(self):
        return [self[name] for name in SHOWCASE_FIELDS]

    def clean(self):
        cleaned = super().clean()
        # 「首页精选」必须先「公开到作品墙」，否则精选了一个外人看不到的东西 ——
        # 首页会显示它、点进去 404。静默纠正而不是报错：勾错的意图是明确的。
        if cleaned.get("is_featured") and not cleaned.get("is_public"):
            cleaned["is_featured"] = False
            self.add_error(
                "is_featured",
                "要先勾「公开到作品墙」才能设为首页精选 —— 否则首页会指向一个外人打不开的页面。",
            )
        return cleaned
