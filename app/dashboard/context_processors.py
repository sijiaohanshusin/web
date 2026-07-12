from django.contrib.auth import get_user_model

from accounts.roles import is_officer


def pending_members(request):
    """仅在驾驶舱页面注入待审核人数（侧边栏徽标用）。"""
    if not request.path.startswith("/dashboard/"):
        return {}
    if not (request.user.is_authenticated and is_officer(request.user)):
        return {}
    User = get_user_model()
    return {"pending_count": User.objects.filter(is_active=False, is_superuser=False).count()}
