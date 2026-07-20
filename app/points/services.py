"""积分读写入口。业务模块 import 本模块，不直接操作 PointLog。"""
from django.db.models import Sum

from .models import PointLog


def award_points(user, delta: int, *, source: str, note: str = "", operator=None) -> PointLog | None:
    """给用户加/扣分。delta 为 0 或用户无效时跳过。"""
    if not getattr(user, "pk", None) or not delta:
        return None
    return PointLog.objects.create(
        user=user, delta=delta, source=source, note=note[:200],
        operator=operator if getattr(operator, "pk", None) else None,
    )


def total_for(user) -> int:
    if not getattr(user, "pk", None):
        return 0
    return user.point_logs.aggregate(total=Sum("delta"))["total"] or 0
