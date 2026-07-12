# -*- coding: utf-8 -*-
"""本地开发演示数据：造几个会员和待审核用户（幂等，仅限本地调试用）。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402

User = get_user_model()
member_group = Group.objects.get(name="会员")

MEMBERS = [
    ("张三", "2025", "信通学院"),
    ("李四", "2025", "智能学院"),
    ("王五", "2024", "信通学院"),
    ("赵六", "2024", "水声学院"),
    ("钱七", "2023", "信通学院"),
]
for i, (name, grade, college) in enumerate(MEMBERS):
    user, created = User.objects.get_or_create(
        username=f"demo{i}",
        defaults={"real_name": name, "grade": grade, "college": college, "student_id": f"20250{i}{i}"},
    )
    if created:
        user.set_password("demo12345")
        user.is_active = True
        user.save()
        user.groups.add(member_group)

PENDING = ["小明", "小红", "小刚"]
for i, name in enumerate(PENDING):
    User.objects.get_or_create(
        username=f"pending{i}",
        defaults={
            "real_name": name, "grade": "2026", "college": "信通学院",
            "student_id": f"20260{i}{i}", "is_active": False,
        },
    )

print("seeded ok, total users:", User.objects.count())
