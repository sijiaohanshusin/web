"""
会员等级体系（member_level 为单一事实来源）。

等级阶梯（对应科协的招募流程）：
    0 待审核      注册后等待通过（自动审核开启时会直接激活为报名会员）
    1 报名会员    已报名，尚未面试
    2 预备会员    通过一轮面试
    3 正式会员    通过二轮面试，正式成员
    4 干事        协会干事，可管理资料、审核会员
    5 管理员      可进入高级后台、管理站点设置

Django Groups 由 member_level 派生（sync_user_groups），仅用于：
- 干事/管理员组附带的资料管理权限（Django Admin 用）
- 论坛彩色头衔的组名映射（见 accounts/sso.py）
"""
LEVEL_PENDING = 0
LEVEL_APPLICANT = 1
LEVEL_PREPARATORY = 2
LEVEL_FORMAL = 3
LEVEL_OFFICER = 4
LEVEL_ADMIN = 5

LEVEL_LABELS = {
    LEVEL_PENDING: "待审核",
    LEVEL_APPLICANT: "报名会员",
    LEVEL_PREPARATORY: "预备会员",
    LEVEL_FORMAL: "正式会员",
    LEVEL_OFFICER: "干事",
    LEVEL_ADMIN: "管理员",
}

LEVEL_CHOICES = [(k, v) for k, v in sorted(LEVEL_LABELS.items())]

# 徽章配色（主站 + 论坛共用同一套色板）
LEVEL_COLORS = {
    LEVEL_PENDING: "#94a3b8",
    LEVEL_APPLICANT: "#38bdf8",
    LEVEL_PREPARATORY: "#0ea5e9",
    LEVEL_FORMAL: "#2563eb",
    LEVEL_OFFICER: "#f59e0b",
    LEVEL_ADMIN: "#ef4444",
}

# 等级 -> Django 组名（同时是论坛头衔组名）。待审核不入组。
LEVEL_GROUP = {
    LEVEL_APPLICANT: "报名会员",
    LEVEL_PREPARATORY: "预备会员",
    LEVEL_FORMAL: "正式会员",
    LEVEL_OFFICER: "干事",
    LEVEL_ADMIN: "管理员",
}
ALL_LEVEL_GROUPS = list(LEVEL_GROUP.values())

# 历史遗留组名（v1），迁移后不再使用，但保留避免破坏旧权限引用
GROUP_MEMBER = "会员"
GROUP_OFFICER = "干事"
GROUP_ADMIN = "管理员"
ALL_GROUPS = ALL_LEVEL_GROUPS


def effective_level(user) -> int:
    """用户的有效等级：超管恒为管理员级；未登录为待审核。"""
    if not getattr(user, "is_authenticated", False):
        return LEVEL_PENDING
    if getattr(user, "is_superuser", False):
        return LEVEL_ADMIN
    return int(getattr(user, "member_level", LEVEL_PENDING) or LEVEL_PENDING)


def is_member(user) -> bool:
    """报名会员及以上，且账号已激活。"""
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return effective_level(user) >= LEVEL_APPLICANT


def is_officer(user) -> bool:
    """干事及以上，可管理资料、审核会员。"""
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return effective_level(user) >= LEVEL_OFFICER


def is_admin(user) -> bool:
    """管理员及以上（含 is_staff / 超管）。"""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return effective_level(user) >= LEVEL_ADMIN


def sync_user_groups(user) -> None:
    """把 member_level 映射为 Django 组成员（幂等）。
    只增删本体系管理的等级组，不动其它组。管理员级自动获得 is_staff。
    """
    from django.contrib.auth.models import Group

    target = LEVEL_GROUP.get(int(user.member_level or 0))
    desired = set()
    if target:
        # 干事及以上同时保留资料管理相关的低阶组，简化权限判断
        desired.add(target)

    managed = set(ALL_LEVEL_GROUPS)
    current = set(user.groups.filter(name__in=managed).values_list("name", flat=True))

    to_add = desired - current
    to_remove = current - desired
    for name in to_add:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    for name in to_remove:
        group = Group.objects.filter(name=name).first()
        if group:
            user.groups.remove(group)

    # 管理员级 -> 工作人员状态（可进 Django Admin）；降级时收回（超管除外）
    if not user.is_superuser:
        should_staff = int(user.member_level or 0) >= LEVEL_ADMIN
        if user.is_staff != should_staff:
            user.is_staff = should_staff
            user.save(update_fields=["is_staff"])
