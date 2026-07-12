from django.contrib.auth.models import AbstractUser
from django.db import models

from . import roles


class User(AbstractUser):
    """协会成员账号。注册后 is_active=False，待管理员审核。"""

    real_name = models.CharField("姓名", max_length=30, blank=True)
    student_id = models.CharField("学号", max_length=20, blank=True, db_index=True)
    college = models.CharField("学院", max_length=50, blank=True)
    grade = models.CharField("年级", max_length=10, blank=True, help_text="入学年份，如 2025")
    qq = models.CharField("QQ 号", max_length=15, blank=True)
    avatar = models.ImageField("头像", upload_to="avatars/", blank=True)

    class Meta(AbstractUser.Meta):
        verbose_name = "成员"
        verbose_name_plural = "成员"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.real_name or self.username

    @property
    def is_member(self) -> bool:
        return roles.is_member(self)

    @property
    def is_officer(self) -> bool:
        return roles.is_officer(self)

    @property
    def role_label(self) -> str:
        if self.is_superuser:
            return "超级管理员"
        names = set(self.groups.values_list("name", flat=True))
        for name in (roles.GROUP_ADMIN, roles.GROUP_OFFICER, roles.GROUP_MEMBER):
            if name in names:
                return name
        if self.is_staff:
            return roles.GROUP_ADMIN
        return "待分配"
