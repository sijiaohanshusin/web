"""站内通知写入口。各业务模块只 import 本模块，不直接操作 Notification。"""
from .models import Notification


def notify_user(user, title: str, *, kind: str = Notification.Kind.SYSTEM,
                body: str = "", url: str = "") -> Notification | None:
    """给单个用户发通知。user 为空（匿名反馈等）时静默跳过。"""
    if not getattr(user, "pk", None):
        return None
    return Notification.objects.create(
        user=user, kind=kind, title=title[:120], body=body[:500], url=url[:300],
    )


def notify_users(users, title: str, *, kind: str = Notification.Kind.SYSTEM,
                 body: str = "", url: str = "") -> int:
    """批量通知（活动提醒、招新放榜等）。返回实际创建条数。"""
    items = [
        Notification(user=u, kind=kind, title=title[:120], body=body[:500], url=url[:300])
        for u in users if getattr(u, "pk", None)
    ]
    Notification.objects.bulk_create(items)
    return len(items)
