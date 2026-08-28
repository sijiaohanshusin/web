from django.contrib import admin

from .models import Honor, Post


@admin.register(Honor)
class HonorAdmin(admin.ModelAdmin):
    """站务日常在 /dashboard/honors/ 录入（等级 4 没有 is_staff、进不来这里）。
    这个 admin 是给管理员批量整理历史记录用的。"""

    list_display = ("year", "level", "title", "contest", "awardee", "is_public", "is_featured")
    list_filter = ("level", "is_public", "is_featured", "year")
    list_editable = ("is_public", "is_featured")
    search_fields = ("title", "contest", "awardee", "note")
    raw_id_fields = ("post",)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "min_level", "pinned", "is_published", "published_at", "author", "view_count")
    list_filter = ("category", "is_published", "pinned", "min_level")
    search_fields = ("title", "body")
    raw_id_fields = ("author",)
    date_hierarchy = "published_at"
