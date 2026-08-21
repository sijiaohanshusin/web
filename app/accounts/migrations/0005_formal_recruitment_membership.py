import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


GROUP_RENAMES = {
    "报名会员": "招新成员",
    "正式会员": "科协会员",
    "干事": "站务管理",
    "管理员": "系统管理员",
}


def prepare_formal_membership(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Position = apps.get_model("accounts", "Position")
    Group = apps.get_model("auth", "Group")

    User.objects.filter(member_level__gte=2).update(registration_channel="returning")
    User.objects.filter(member_level__gte=2).update(specialty="custom", specialty_custom="待补充")

    grade_aliases = {"2023级": "2023", "22级": "2022"}
    for old, new in grade_aliases.items():
        User.objects.filter(grade=old).update(grade=new)

    college_aliases = ["信息和通信工程学院", "信通", "信息与通信工程", "信通学院"]
    User.objects.filter(college__in=college_aliases).update(college="信息与通信工程学院")

    positions = [
        ("主席", "#b8860b", True, 10),
        ("硬件主席", "#c98a3d", True, 20),
        ("软件主席", "#0da9cd", True, 30),
        ("硬件副主席", "#d97706", False, 40),
        ("软件副主席", "#0284c7", False, 50),
    ]
    for name, color, grants, order in positions:
        Position.objects.update_or_create(
            name=name,
            defaults={"color": color, "grants_management": grants, "sort_order": order},
        )

    for old_name, new_name in GROUP_RENAMES.items():
        old = Group.objects.filter(name=old_name).first()
        if not old:
            Group.objects.get_or_create(name=new_name)
            continue
        target = Group.objects.filter(name=new_name).first()
        if target:
            target.permissions.add(*old.permissions.all())
            target.user_set.add(*old.user_set.all())
            old.delete()
        else:
            old.name = new_name
            old.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_alter_medal_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="grants_management",
            field=models.BooleanField(default=False, verbose_name="授予管理驾驶舱权限"),
        ),
        migrations.AddField(
            model_name="user",
            name="registration_channel",
            field=models.CharField(choices=[("new", "新会员通道"), ("returning", "老会员通道")], db_index=True, default="new", max_length=12, verbose_name="注册通道"),
        ),
        migrations.AddField(
            model_name="user",
            name="specialty",
            field=models.CharField(choices=[("hardware", "硬件"), ("software", "软件"), ("custom", "自定义")], default="hardware", max_length=12, verbose_name="擅长方向"),
        ),
        migrations.AddField(
            model_name="user",
            name="specialty_custom",
            field=models.CharField(blank=True, max_length=60, verbose_name="自定义方向"),
        ),
        migrations.AlterField(
            model_name="user", name="member_level",
            field=models.PositiveSmallIntegerField(choices=[(0, "待审核"), (1, "招新成员"), (2, "预备会员"), (3, "科协会员"), (4, "站务管理"), (5, "系统管理员")], db_index=True, default=0, verbose_name="会员等级"),
        ),
        migrations.AlterField(
            model_name="levellog", name="from_level",
            field=models.PositiveSmallIntegerField(choices=[(0, "待审核"), (1, "招新成员"), (2, "预备会员"), (3, "科协会员"), (4, "站务管理"), (5, "系统管理员")], verbose_name="原等级"),
        ),
        migrations.AlterField(
            model_name="levellog", name="to_level",
            field=models.PositiveSmallIntegerField(choices=[(0, "待审核"), (1, "招新成员"), (2, "预备会员"), (3, "科协会员"), (4, "站务管理"), (5, "系统管理员")], verbose_name="新等级"),
        ),
        migrations.CreateModel(
            name="ReturningMembershipRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_role", models.CharField(choices=[("member", "科协会员"), ("chair", "主席"), ("hardware_chair", "硬件主席"), ("software_chair", "软件主席"), ("hardware_vice_chair", "硬件副主席"), ("software_vice_chair", "软件副主席")], max_length=24, verbose_name="申报身份")),
                ("status", models.CharField(choices=[("pending", "待审核"), ("approved", "已通过"), ("rejected", "已拒绝")], db_index=True, default="pending", max_length=12, verbose_name="审核状态")),
                ("review_note", models.CharField(blank=True, max_length=200, verbose_name="审核备注")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="审核时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="申请时间")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="returning_requests_reviewed", to=settings.AUTH_USER_MODEL, verbose_name="审核人")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="returning_request", to=settings.AUTH_USER_MODEL, verbose_name="申请账号")),
            ],
            options={"verbose_name": "老会员身份恢复申请", "verbose_name_plural": "老会员身份恢复申请", "ordering": ["-created_at"]},
        ),
        migrations.RunPython(prepare_formal_membership, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(condition=~Q(student_id=""), fields=("student_id",), name="uniq_nonblank_student_id"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(condition=~Q(phone=""), fields=("phone",), name="uniq_nonblank_phone"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower("email"), condition=~Q(email=""), name="uniq_nonblank_email_ci"),
        ),
    ]
