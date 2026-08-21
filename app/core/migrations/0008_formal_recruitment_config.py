from django.db import migrations, models


def close_beta_and_update_qq(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    config, _ = SiteConfig.objects.get_or_create(pk=1)
    config.recruit_qq_group = "1081376858"
    config.beta_mode = False
    config.auto_approve = False
    config.save(update_fields=["recruit_qq_group", "beta_mode", "auto_approve"])


class Migration(migrations.Migration):
    dependencies = [("core", "0007_siteconfig_featured_video_bvids")]

    operations = [
        migrations.AlterField(model_name="siteconfig", name="recruit_qq_group", field=models.CharField(default="1081376858", max_length=20, verbose_name="招新 QQ 群号")),
        migrations.AlterField(model_name="siteconfig", name="beta_mode", field=models.BooleanField(default=False, editable=False, help_text="正式招新版本不再使用此开关。", verbose_name="内测模式（已停用）")),
        migrations.AlterField(model_name="siteconfig", name="auto_approve", field=models.BooleanField(default=False, editable=False, help_text="正式版本改用新会员自动激活、老会员单独审核。", verbose_name="旧版自动审核（已停用）")),
        migrations.AlterModelOptions(name="feedback", options={"ordering": ["-created_at"], "verbose_name": "网站问题反馈", "verbose_name_plural": "网站问题反馈"}),
        migrations.RunPython(close_beta_and_update_qq, migrations.RunPython.noop),
    ]
