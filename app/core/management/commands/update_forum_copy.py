"""Replace only the obsolete forum sentence in active recruitment campaigns."""
from django.core.management.base import BaseCommand
from recruitment.models import Campaign

OLD = '报名期间仅开放公开内容；会员资料、活动报名和论坛权限将在通过一面后开放。'
NEW = ('新会员注册并验证邮箱后即可在论坛公共板块发帖、回复，无需等待面试。'
       '会员资料、活动及内部交流板块按等级逐步开放；高等级会员可选择相应内部板块发布限定等级可见的帖子。')


class Command(BaseCommand):
    help = 'Preview the exact outdated recruitment sentence replacement; --apply to save.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        for campaign in Campaign.objects.filter(is_active=True, intro__contains=OLD):
            if options['apply']:
                changed = Campaign.objects.filter(pk=campaign.pk, intro=campaign.intro).update(
                    intro=campaign.intro.replace(OLD, NEW))
                if changed != 1:
                    raise RuntimeError('Campaign changed concurrently; review before retrying')
            self.stdout.write(f'{"Updated" if options["apply"] else "Would update"} campaign {campaign.pk}')
