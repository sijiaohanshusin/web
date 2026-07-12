from django.contrib import admin

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "visibility", "uploader", "size_display", "download_count", "created_at"]
    list_filter = ["category", "visibility"]
    search_fields = ["title", "description"]
    readonly_fields = ["size", "download_count"]

    @admin.display(description="大小")
    def size_display(self, obj):
        size = obj.size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size /= 1024
        return f"{size:.1f} TB"
