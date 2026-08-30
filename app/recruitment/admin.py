from django.contrib import admin

from .models import Application, Campaign


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "opens_at", "closes_at", "is_active", "status_label")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """站务日常在 `/dashboard/recruitment/` 上做事（等级 4 没有 is_staff，打不开
    这里），所以这一屏实际只有管理员用 —— 定位是「救数据」，不是日常流程。

    **`interests` / `heard_from` 不放进 `list_filter`**：Django 给 `JSONField` 的
    过滤器是按整个数组精确匹配的，`["mcu"]` 和 `["mcu","power"]` 会变成两个互不
    相干的选项，选项列表长度等于「出现过的组合数」—— 那不是能用的筛选。要按项看
    分布去 `/dashboard/recruitment/`，那一页有专门的两块。
    """

    list_display = ("id", "user", "campaign", "department", "interests_display",
                    "status", "created_at")
    list_filter = ("status", "department", "campaign")
    search_fields = (
        "user__username", "user__real_name", "user__student_id",
        "skills", "self_intro", "first_impression", "motto",
        "interests_other", "heard_from_other",
    )
    raw_id_fields = ("campaign", "user")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("campaign", "user", "status", "interview_note")}),
        ("答卷", {"fields": (
            "department", "interests", "interests_other",
            "skills", "self_intro", "first_impression", "motto",
            "heard_from", "heard_from_other",
        )}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="兴趣方向")
    def interests_display(self, obj):
        return obj.interests_display or "—"
