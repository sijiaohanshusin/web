from django.db import migrations
from django.utils import timezone


INTRO = """## 2026 秋季招新

电子科技协会面向全校同学开放报名，无论是否有基础，都欢迎从动手实践开始。

1. 完成新会员注册并提交本页报名表。
2. 加入招新 QQ 群 **1081376858**，留意面试安排。
3. 一面通过后成为预备会员，二面通过后成为科协会员。

报名期间仅开放公开内容；会员资料、活动报名和论坛权限将在通过一面后开放。
"""


def open_campaign(apps, schema_editor):
    Campaign = apps.get_model("recruitment", "Campaign")
    campaign, created = Campaign.objects.get_or_create(
        name="2026 秋季招新",
        defaults={"intro": INTRO, "opens_at": timezone.now(), "closes_at": None, "is_active": True},
    )
    if not created:
        campaign.intro = campaign.intro or INTRO
        campaign.closes_at = None
        campaign.is_active = True
        if campaign.opens_at > timezone.now():
            campaign.opens_at = timezone.now()
        campaign.save(update_fields=["intro", "opens_at", "closes_at", "is_active"])


class Migration(migrations.Migration):
    dependencies = [("recruitment", "0001_initial"), ("accounts", "0005_formal_recruitment_membership")]
    operations = [migrations.RunPython(open_campaign, migrations.RunPython.noop)]
