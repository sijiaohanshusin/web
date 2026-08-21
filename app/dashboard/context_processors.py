from django.contrib.auth import get_user_model

from accounts.roles import is_officer
from accounts.models import ReturningMembershipRequest
from core.models import Feedback


def pending_members(request):
    """仅在驾驶舱页面注入待办数字（侧边栏徽标用）。"""
    if not request.path.startswith("/dashboard/"):
        return {}
    if not (request.user.is_authenticated and is_officer(request.user)):
        return {}
    User = get_user_model()
    return {
        "pending_count": ReturningMembershipRequest.objects.filter(
            status=ReturningMembershipRequest.Status.PENDING,
        ).count(),
        "feedback_pending": Feedback.objects.filter(status=Feedback.Status.PENDING).count(),
    }
