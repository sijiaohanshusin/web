from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from . import roles
from .models import LevelLog, Medal, Position, User, UserMedal, VerificationCode


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = [
        "username", "real_name", "student_id", "college", "grade",
        "member_level", "position", "is_active", "date_joined",
    ]
    list_filter = ["member_level", "is_active", "position", "grade", "college"]
    search_fields = ["username", "real_name", "student_id", "qq", "phone", "email"]
    ordering = ["-date_joined"]
    actions = ["approve_as_applicant", "promote_formal"]

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("协会信息", {"fields": (
            "real_name", "student_id", "college", "grade", "qq", "phone", "avatar",
            "member_level", "position",
        )}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("协会信息", {"fields": ("real_name", "student_id", "college", "grade", "qq", "phone", "member_level")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        roles.sync_user_groups(obj)  # 后台改等级后同步 Django 组与 is_staff

    @admin.action(description="通过审核（设为报名会员）")
    def approve_as_applicant(self, request, queryset):
        count = 0
        for user in queryset:
            user.set_level(roles.LEVEL_APPLICANT, actor=request.user, note="Admin 批量审核")
            count += 1
        self.message_user(request, f"已通过 {count} 名成员的审核。")

    @admin.action(description="晋升为正式会员")
    def promote_formal(self, request, queryset):
        count = 0
        for user in queryset:
            user.set_level(roles.LEVEL_FORMAL, actor=request.user, note="Admin 批量晋升")
            count += 1
        self.message_user(request, f"已将 {count} 名成员晋升为正式会员。")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "sort_order"]
    list_editable = ["sort_order"]


@admin.register(Medal)
class MedalAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color", "sort_order", "description"]
    list_editable = ["sort_order"]
    search_fields = ["name"]


@admin.register(UserMedal)
class UserMedalAdmin(admin.ModelAdmin):
    list_display = ["user", "medal", "reason", "granted_by", "created_at"]
    search_fields = ["user__username", "user__real_name", "medal__name"]
    autocomplete_fields = ["user", "medal", "granted_by"]


@admin.register(LevelLog)
class LevelLogAdmin(admin.ModelAdmin):
    list_display = ["user", "from_level", "to_level", "operator", "created_at"]
    search_fields = ["user__username", "user__real_name"]
    readonly_fields = ["user", "from_level", "to_level", "operator", "note", "created_at"]


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ["email", "purpose", "code", "used", "attempts", "created_at"]
    list_filter = ["purpose", "used"]
    search_fields = ["email"]
