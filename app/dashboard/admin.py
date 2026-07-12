from django.contrib import admin

from .models import BiliSnapshot


@admin.register(BiliSnapshot)
class BiliSnapshotAdmin(admin.ModelAdmin):
    list_display = ["date", "follower", "videos", "likes"]
    ordering = ["-date"]
