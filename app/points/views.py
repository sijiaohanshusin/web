from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import render

from accounts.roles import is_member

from . import services

User = get_user_model()


@login_required
def mine(request):
    if not is_member(request.user):
        return HttpResponseForbidden("积分功能将在通过一轮面试后开放。")
    logs = request.user.point_logs.select_related("operator")
    paginator = Paginator(logs, 20)
    page = paginator.get_page(request.GET.get("page"))
    context = {
        "total": services.total_for(request.user),
        "page": page,
    }
    return render(request, "points/mine.html", context)


def leaderboard(request):
    """积分排行榜（前 50，需有积分流水）。"""
    rows = (
        User.objects.filter(is_active=True, point_logs__isnull=False)
        .annotate(total=Sum("point_logs__delta"))
        .filter(total__gt=0)
        .select_related("position")
        .order_by("-total", "date_joined")[:50]
    )
    my_total = services.total_for(request.user) if request.user.is_authenticated else None
    context = {
        "rows": rows,
        "my_total": my_total,
    }
    return render(request, "points/leaderboard.html", context)
