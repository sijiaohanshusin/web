from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "min_level", "pinned", "is_published", "published_at", "author", "view_count")
    list_filter = ("category", "is_published", "pinned", "min_level")
    search_fields = ("title", "body")
    raw_id_fields = ("author",)
    date_hierarchy = "published_at"
