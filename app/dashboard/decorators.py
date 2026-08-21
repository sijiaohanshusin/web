from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from accounts.roles import is_officer


def officer_required(view_func):
    """站务管理或获授权主席可访问；未登录跳登录页。"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_officer(request.user):
            raise PermissionDenied("需要站务管理权限")
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """管理员（工作人员/超管）可访问。"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("需要管理员权限")
        return view_func(request, *args, **kwargs)

    return wrapper
