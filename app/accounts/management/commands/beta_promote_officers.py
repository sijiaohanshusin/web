"""
内测阶段：把所有已激活的普通成员（等级 < 干事）提升为干事，方便测试全部功能。
超管不动。用法：python manage.py beta_promote_officers
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts import roles

User = get_user_model()


class Command(BaseCommand):
    help = "内测：将已激活成员批量提升为干事"

    def handle(self, *args, **options):
        qs = User.objects.filter(is_active=True, is_superuser=False, member_level__lt=roles.LEVEL_OFFICER)
        count = 0
        for user in qs:
            user.set_level(roles.LEVEL_OFFICER, note="内测批量提升为干事")
            count += 1
        self.stdout.write(self.style.SUCCESS(f"已将 {count} 名成员提升为干事。"))
