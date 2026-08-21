from django.db import migrations, models


def promote_applicant_visibility(apps, schema_editor):
    apps.get_model("news", "Post").objects.filter(min_level=1).update(min_level=2)


class Migration(migrations.Migration):
    dependencies = [("news", "0001_initial")]
    operations = [
        migrations.RunPython(promote_applicant_visibility, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="post", name="min_level",
            field=models.PositiveSmallIntegerField(choices=[(0, "公开（所有人）"), (2, "预备会员及以上"), (3, "科协会员及以上"), (4, "站务管理及以上")], default=0, help_text="达到该等级的成员才能看到这篇公告", verbose_name="可见等级"),
        ),
    ]
