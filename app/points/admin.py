from django.contrib import admin

from .models import PointLog


@admin.register(PointLog)
class PointLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "delta", "source", "note", "operator", "created_at")
    list_filter = ("source",)
    search_fields = ("note", "user__username", "user__real_name")
    raw_id_fields = ("user", "operator")
    date_hierarchy = "created_at"
