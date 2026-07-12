from django.contrib import admin
from django.utils.html import format_html

from .models import CarouselImage, SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """单例配置：禁止新增/删除，只能修改唯一的一条。"""

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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
