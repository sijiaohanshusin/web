from django.contrib import admin

from .models import Application, Campaign


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "opens_at", "closes_at", "is_active", "status_label")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "campaign", "department", "status", "created_at")
    list_filter = ("status", "department", "campaign")
    search_fields = ("user__username", "user__real_name", "user__student_id", "skills")
    raw_id_fields = ("campaign", "user")
