"""
角色体系（基于 Django Groups）：

- 会员：注册并通过审核的普通成员，可访问“仅会员”资料
- 干事：协会干事，可在前台上传/管理资料
- 管理员：可登录 Django Admin 后台（需同时勾选“工作人员状态”）

新注册用户 is_active=False（待审核），管理员在后台批量“通过审核”。
"""
GROUP_MEMBER = "会员"
GROUP_OFFICER = "干事"
GROUP_ADMIN = "管理员"

ALL_GROUPS = [GROUP_MEMBER, GROUP_OFFICER, GROUP_ADMIN]


def is_member(user) -> bool:
    """已审核会员（干事/管理员/超管自然也算会员）。"""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=ALL_GROUPS).exists()


def is_officer(user) -> bool:
    """干事及以上，可管理资料。"""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=[GROUP_OFFICER, GROUP_ADMIN]).exists()
