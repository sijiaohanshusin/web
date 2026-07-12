"""
创建角色用户组（会员 / 干事 / 管理员）并给干事、管理员分配资料管理权限。
"""
from django.db import migrations

GROUPS = ["会员", "干事", "管理员"]
RESOURCE_PERMS = ["add_resource", "change_resource", "delete_resource", "view_resource"]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Resource = apps.get_model("files", "Resource")

    groups = {name: Group.objects.get_or_create(name=name)[0] for name in GROUPS}

    # 迁移过程中 post_migrate 还没跑，权限可能不存在，这里显式补齐
    content_type = ContentType.objects.get_for_model(Resource)
    perm_labels = {
        "add_resource": "Can add 资料",
        "change_resource": "Can change 资料",
        "delete_resource": "Can delete 资料",
        "view_resource": "Can view 资料",
    }
    perms = []
    for codename in RESOURCE_PERMS:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": perm_labels[codename]},
        )
        perms.append(perm)

    groups["干事"].permissions.add(*perms)
    groups["管理员"].permissions.add(*perms)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("files", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
