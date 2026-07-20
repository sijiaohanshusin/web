from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "title", "read_at", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "body", "user__username", "user__real_name")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
