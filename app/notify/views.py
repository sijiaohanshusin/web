from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    qs = request.user.notifications.all()
    tab = request.GET.get("tab", "all")
    if tab == "unread":
        qs = qs.filter(read_at__isnull=True)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    context = {
        "page": page,
        "tab": tab,
        "unread_count": request.user.notifications.filter(read_at__isnull=True).count(),
    }
    return render(request, "notify/list.html", context)


@login_required
def notification_go(request, pk: int):
    """点击通知：标记已读并跳到目标页。"""
    item = get_object_or_404(Notification, pk=pk, user=request.user)
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    # url 只由服务端业务代码写入（站内相对路径），不接受用户输入
    if item.url and item.url.startswith("/"):
        return redirect(item.url)
    return redirect("notify:list")


@login_required
@require_POST
def mark_all_read(request):
    updated = request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    if updated:
        messages.success(request, f"已将 {updated} 条通知标记为已读。")
    return redirect(request.POST.get("next") or "notify:list")


@login_required
def latest_json(request):
    """铃铛下拉：最近 8 条（懒加载，点开铃铛才请求）。"""
    items = list(request.user.notifications.all()[:8])
    return JsonResponse({
        "unread": request.user.notifications.filter(read_at__isnull=True).count(),
        "items": [
            {
                "id": n.pk,
                "kind": n.get_kind_display(),
                "title": n.title,
                "body": n.body,
                "time": naturaltime(n.created_at),
                "read": n.is_read,
            }
            for n in items
        ],
    })
