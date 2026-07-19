"""
数据迁移：把 v1 的 Django 组成员回填为 member_level，并建齐 v2 等级组。

映射：管理员/超管 -> 5；干事 -> 4；会员 -> 3（正式会员）；
      其余已激活用户 -> 3；未激活 -> 0（待审核）。
"""
from django.db import migrations

NEW_GROUPS = ["报名会员", "预备会员", "正式会员", "干事", "管理员"]
LEVEL_GROUP = {1: "报名会员", 2: "预备会员", 3: "正式会员", 4: "干事", 5: "管理员"}


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Group = apps.get_model("auth", "Group")

    for name in NEW_GROUPS:
        Group.objects.get_or_create(name=name)
    groups = {g.name: g for g in Group.objects.filter(name__in=NEW_GROUPS)}

    for user in User.objects.all().prefetch_related("groups"):
        current = set(user.groups.values_list("name", flat=True))
        if user.is_superuser or user.is_staff or "管理员" in current:
            level = 5
        elif "干事" in current:
            level = 4
        elif user.is_active:
            level = 3  # 老"会员" -> 正式会员
        else:
            level = 0

        user.member_level = level
        user.save(update_fields=["member_level"])

        # 归一化组：清掉本体系管理的组，按等级重新加一个
        managed = user.groups.filter(name__in=NEW_GROUPS + ["会员"])
        for g in managed:
            user.groups.remove(g)
        target = LEVEL_GROUP.get(level)
        if target:
            user.groups.add(groups[target])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_medal_position_user_member_level_user_phone_levellog_and_more"),
        ("files", "0002_create_groups"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
