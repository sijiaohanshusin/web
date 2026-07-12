from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from . import roles
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = [
        "username", "real_name", "student_id", "college", "grade",
        "role_display", "is_active", "date_joined",
    ]
    list_filter = ["is_active", "groups", "grade", "college"]
    search_fields = ["username", "real_name", "student_id", "qq"]
    ordering = ["-date_joined"]
    actions = ["approve_as_member"]

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("协会信息", {"fields": ("real_name", "student_id", "college", "grade", "qq", "avatar")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("协会信息", {"fields": ("real_name", "student_id", "college", "grade", "qq")}),
    )

    @admin.display(description="角色")
    def role_display(self, obj):
        return obj.role_label

    @admin.action(description="通过审核并设为会员")
    def approve_as_member(self, request, queryset):
        member_group = Group.objects.get(name=roles.GROUP_MEMBER)
        count = 0
        for user in queryset:
            user.is_active = True
            user.save(update_fields=["is_active"])
            user.groups.add(member_group)
            count += 1
        self.message_user(request, f"已通过 {count} 名成员的审核。")
