from django.contrib.auth import get_user_model

from accounts.roles import is_officer
from accounts.models import ReturningMembershipRequest
from core import slots as slot_registry
from core.models import Feedback, MediaSlot


def pending_members(request):
    """仅在驾驶舱页面注入待办数字（侧边栏徽标用）。"""
    if not request.path.startswith("/dashboard/"):
        return {}
    if not (request.user.is_authenticated and is_officer(request.user)):
        return {}
    User = get_user_model()
    # 缺图数：登记表里既没有启用的上传、也没有兜底静态图的槽位。
    # 从登记表出发而不是从 MediaSlot 表出发 —— 没建行的槽位才是要补的那些。
    have = set(MediaSlot.objects.filter(is_active=True).values_list("key", flat=True))
    missing = sum(1 for spec in slot_registry.SLOTS
                  if spec.key not in have and not spec.fallback)
    return {
        "pending_count": ReturningMembershipRequest.objects.filter(
            status=ReturningMembershipRequest.Status.PENDING,
        ).count(),
        "feedback_pending": Feedback.objects.filter(status=Feedback.Status.PENDING).count(),
        "media_missing": missing,
    }
