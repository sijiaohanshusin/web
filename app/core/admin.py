from django import forms
from django.contrib import admin
from django.utils.html import format_html

from . import slots as slot_registry
from .models import CarouselImage, Feedback, FeedbackReply, MediaSlot, SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """单例配置：禁止新增/删除，只能修改唯一的一条。"""

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class FeedbackReplyInline(admin.TabularInline):
    model = FeedbackReply
    extra = 0
    readonly_fields = ["author", "content", "created_at"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    inlines = [FeedbackReplyInline]
    list_display = ["id", "short_content", "user", "contact", "status", "created_at", "resolved_by"]
    list_filter = ["status"]
    search_fields = ["content", "contact", "user__username", "user__real_name"]
    readonly_fields = ["user", "contact", "page", "content", "created_at"]

    @admin.display(description="内容")
    def short_content(self, obj):
        return obj.content[:40]


@admin.register(CarouselImage)
class CarouselImageAdmin(admin.ModelAdmin):
    list_display = ["preview", "title", "caption", "sort_order", "is_active", "created_at"]
    list_editable = ["sort_order", "is_active"]
    list_display_links = ["preview", "title"]

    @admin.display(description="预览")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:48px;border-radius:4px;">', obj.image.url)
        return "-"


class MediaSlotForm(forms.ModelForm):
    """key 改成下拉选，选项来自登记表。

    手打这个字符串必然会有拼错的时候，而拼错的后果是那个位置永远显示占位框 ——
    页面不报错、日志没东西，没人会发现。让它只能从登记表里选。
    """

    key = forms.ChoiceField(label="槽位标识")

    class Meta:
        model = MediaSlot
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["key"].choices = [
            (spec.key, f"{spec.group} · {spec.label}（{spec.ratio}）")
            for spec in slot_registry.SLOTS
        ]


@admin.register(MediaSlot)
class MediaSlotAdmin(admin.ModelAdmin):
    """素材槽内容。槽位本身在 core/slots.py 声明，这里只管往里填图。"""

    list_display = ["preview", "key", "slot_label", "alt", "is_active", "updated_at", "updated_by"]
    list_editable = ["is_active"]
    list_display_links = ["preview", "key"]
    search_fields = ["key", "alt", "caption"]
    readonly_fields = ["width", "height", "updated_at", "updated_by", "requirement"]
    fields = ["key", "requirement", "image", "alt", "caption", "credit",
              "focal_x", "focal_y", "is_active", "width", "height",
              "updated_at", "updated_by"]

    form = MediaSlotForm

    @admin.display(description="拍摄要求")
    def requirement(self, obj):
        spec = slot_registry.get(obj.key) if obj and obj.key else None
        if not spec:
            return "—"
        return format_html("<strong>{}</strong><br>{}<br><small>比例 {}</small>",
                           spec.label, spec.brief, spec.ratio)

    @admin.display(description="槽位名称")
    def slot_label(self, obj):
        spec = slot_registry.get(obj.key)
        return spec.label if spec else "（未登记）"

    @admin.display(description="预览")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:48px;border-radius:4px;">', obj.image.url)
        return "-"

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
