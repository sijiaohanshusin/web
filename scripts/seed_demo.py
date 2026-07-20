# -*- coding: utf-8 -*-
"""本地开发演示数据：会员、待审核用户、公告、通知（幂等，仅限本地调试用）。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from datetime import timedelta  # noqa: E402

from django.utils import timezone  # noqa: E402

from accounts import roles  # noqa: E402
from news.models import Post  # noqa: E402
from notify.services import notify_user  # noqa: E402
from recruitment.models import Application, Campaign  # noqa: E402

User = get_user_model()

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
        user.set_level(roles.LEVEL_FORMAL, note="演示数据")

PENDING = ["小明", "小红", "小刚"]
for i, name in enumerate(PENDING):
    User.objects.get_or_create(
        username=f"pending{i}",
        defaults={
            "real_name": name, "grade": "2026", "college": "信通学院",
            "student_id": f"20260{i}{i}", "is_active": False,
        },
    )

author = User.objects.filter(username="demo0").first()
POSTS = [
    ("2026 秋季招新即将启动", Post.Category.NOTICE, "# 招新啦\n\n**9 月开学季**，欢迎 2026 级新同学！\n\n- 免费培训\n- 实验室开放\n- 电赛梯队", True),
    ("暑期电赛集训队获佳绩", Post.Category.HONOR, "恭喜我协成员在 2026 年电子设计竞赛中获得 **国家一等奖** 2 项！", False),
    ("资料站新增运放专题课件", Post.Category.ACTIVITY, "学习中心与资料站同步更新第 4 章运放高级应用配套课件，欢迎下载。", False),
]
for title, category, body, pinned in POSTS:
    _, created = Post.objects.get_or_create(
        title=title, defaults={"category": category, "body": body, "pinned": pinned, "author": author},
    )
    if created and author:
        notify_user(author, f"演示：你发布的「{title}」已上线", kind="news", url="/news/")

campaign, _ = Campaign.objects.get_or_create(
    name="2026 秋季招新",
    defaults={
        "intro": "## 欢迎加入电子科技协会\n\n- 面向全体本科新生\n- 硬件部 / 软件部两个方向\n- 流程：报名 → 一面 → 暑期培训 → 二面",
        "opens_at": timezone.now() - timedelta(days=2),
        "closes_at": timezone.now() + timedelta(days=30),
        "is_active": True,
    },
)
for i in range(3):
    applicant = User.objects.filter(username=f"pending{i}").first()
    if applicant:
        applicant.set_level(roles.LEVEL_APPLICANT, note="演示：招新报名")
        Application.objects.get_or_create(
            campaign=campaign, user=applicant,
            defaults={
                "department": ["hardware", "software", "undecided"][i],
                "skills": ["会一点 C", "焊过板子", "零基础但很想学"][i],
                "self_intro": "演示报名者的自我介绍，说明为什么想加入以及期待收获。",
            },
        )

print("seeded ok, users:", User.objects.count(), "posts:", Post.objects.count(),
      "applications:", Application.objects.count())
