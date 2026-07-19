from django.contrib import admin
from django.utils.html import format_html

from .models import CarouselImage, Feedback, SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """单例配置：禁止新增/删除，只能修改唯一的一条。"""

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
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
