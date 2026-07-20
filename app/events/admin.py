from django.contrib import admin

from .models import Event, EventSignup


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "kind", "start_at", "end_at", "capacity", "min_level",
                    "points_reward", "is_published", "checkin_open")
    list_filter = ("kind", "is_published")
    search_fields = ("title", "description", "location")
    date_hierarchy = "start_at"


@admin.register(EventSignup)
class EventSignupAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "user", "is_walkin", "checkin_at", "created_at")
    list_filter = ("is_walkin",)
    search_fields = ("event__title", "user__username", "user__real_name")
    raw_id_fields = ("event", "user")
