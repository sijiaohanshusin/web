"""项目档案库的访问控制小工具。"""
from accounts.roles import is_member, is_officer

from .models import ProjectMember


def membership(user, project):
    """返回用户在项目中的成员记录，不是成员则 None。"""
    if not getattr(user, "is_authenticated", False):
        return None
    return ProjectMember.objects.filter(project=project, user=user).first()


def can_view_list(user) -> bool:
    """报名会员及以上可以浏览项目名片列表。"""
    return is_member(user)


def can_view_files(user, project) -> bool:
    """项目成员或干事及以上可以查看/下载项目内文件。"""
    return is_officer(user) or membership(user, project) is not None


def can_edit(user, project) -> bool:
    """项目成员（含负责人）或干事及以上可以上传、建目录、删除文件。"""
    return is_officer(user) or membership(user, project) is not None


def can_manage(user, project) -> bool:
    """负责人或干事及以上可以管理成员、归档、删除项目。"""
    if is_officer(user):
        return True
    m = membership(user, project)
    return m is not None and m.role == ProjectMember.Role.LEAD
