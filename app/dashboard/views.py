import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.utils import timezone

import uuid

from accounts import roles
from accounts.models import Medal, Position, UserMedal
from core import bilibili
from core.models import CarouselImage, Feedback, SiteConfig
from events.forms import EventForm
from events.models import Event, EventSignup
from files.forms import ResourceUploadForm
from files.models import Resource
from news.forms import PostForm
from news.models import Post
from notify.models import Notification
from notify.services import notify_user
from points.models import PointLog
from points.services import award_points
from recruitment.forms import CampaignForm
from recruitment.models import Application, Campaign
from projects.forms import ProjectForm
from projects.models import Project, ProjectMember

from .decorators import admin_required, officer_required
from .forms import CarouselImageForm, SiteConfigForm
from .models import BiliSnapshot

User = get_user_model()


def _is_admin(user) -> bool:
    return user.is_staff or user.is_superuser


# ---------------------------------------------------------------- 总览

def _month_labels(n=12):
    """返回最近 n 个月的月初日期列表（含本月），升序。"""
    today = datetime.date.today().replace(day=1)
    result = []
    year, month = today.year, today.month
    for _ in range(n):
        result.append(datetime.date(year, month, 1))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(result))


@officer_required
def overview(request):
    config = SiteConfig.load()

    total_members = User.objects.filter(is_active=True).count()
    pending_count = User.objects.filter(member_level=roles.LEVEL_PENDING, is_superuser=False).count()
    officer_count = User.objects.filter(
        Q(member_level__gte=roles.LEVEL_OFFICER) | Q(is_staff=True), is_active=True
    ).distinct().count()
    resource_count = Resource.objects.count()
    download_total = Resource.objects.aggregate(total=Sum("download_count"))["total"] or 0

    stats = bilibili.get_stats(config.bilibili_mid)
    # 每天第一次打开总览时落一条快照，日积月累形成趋势
    if stats:
        BiliSnapshot.objects.get_or_create(
            date=datetime.date.today(),
            defaults={"follower": stats["follower"], "videos": stats["videos"], "likes": stats["likes"]},
        )

    # 注册趋势（近 12 个月）
    months = _month_labels(12)
    reg_rows = (
        User.objects.filter(date_joined__date__gte=months[0])
        .annotate(m=TruncMonth("date_joined"))
        .values("m")
        .annotate(c=Count("id"))
    )
    reg_map = {row["m"].date() if hasattr(row["m"], "date") else row["m"]: row["c"] for row in reg_rows}
    reg_trend = {
        "labels": [f"{m.year}-{m.month:02d}" for m in months],
        "data": [reg_map.get(m, 0) for m in months],
    }

    # 年级分布
    grade_rows = (
        User.objects.filter(is_active=True)
        .exclude(grade="")
        .values("grade")
        .annotate(c=Count("id"))
        .order_by("grade")
    )
    grade_dist = {
        "labels": [r["grade"] + " 级" for r in grade_rows],
        "data": [r["c"] for r in grade_rows],
    }

    # 资料分类分布
    cat_labels = dict(Resource.Category.choices)
    cat_rows = Resource.objects.values("category").annotate(c=Count("id"))
    category_dist = {
        "labels": [cat_labels.get(r["category"], r["category"]) for r in cat_rows],
        "data": [r["c"] for r in cat_rows],
    }

    # 下载 Top 10
    top = list(Resource.objects.filter(download_count__gt=0).order_by("-download_count")[:10])
    top_downloads = {
        "labels": [r.title[:16] + ("…" if len(r.title) > 16 else "") for r in top],
        "data": [r.download_count for r in top],
    }

    # B 站粉丝走势（最近 90 条快照）
    snaps = list(BiliSnapshot.objects.order_by("-date")[:90])[::-1]
    bili_trend = {
        "labels": [s.date.strftime("%m-%d") for s in snaps],
        "data": [s.follower for s in snaps],
    }

    context = {
        "active_nav": "overview",
        "total_members": total_members,
        "pending_count": pending_count,
        "officer_count": officer_count,
        "resource_count": resource_count,
        "download_total": download_total,
        "bili_stats": stats,
        "charts": {
            "regTrend": reg_trend,
            "gradeDist": grade_dist,
            "categoryDist": category_dist,
            "topDownloads": top_downloads,
            "biliTrend": bili_trend,
        },
    }
    return render(request, "dashboard/overview.html", context)


# ---------------------------------------------------------------- 会员管理

@officer_required
def members(request):
    tab = request.GET.get("tab", "")
    if tab not in ("pending", "all"):
        tab = "pending" if User.objects.filter(member_level=roles.LEVEL_PENDING, is_superuser=False).exists() else "all"

    users = User.objects.select_related("position").annotate(medal_count=Count("medals")).order_by("-date_joined")
    if tab == "pending":
        users = users.filter(member_level=roles.LEVEL_PENDING, is_superuser=False)

    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(username__icontains=query) | Q(real_name__icontains=query)
            | Q(student_id__icontains=query) | Q(qq__icontains=query)
            | Q(phone__icontains=query) | Q(college__icontains=query)
        )

    grade = request.GET.get("grade", "").strip()
    if grade:
        users = users.filter(grade=grade)

    level = request.GET.get("level", "")
    if level.isdigit():
        users = users.filter(member_level=int(level))

    paginator = Paginator(users.distinct(), 25)
    page = paginator.get_page(request.GET.get("page"))

    grades = (
        User.objects.exclude(grade="").values_list("grade", flat=True).distinct().order_by("grade")
    )

    context = {
        "active_nav": "members",
        "tab": tab,
        "page": page,
        "query": query,
        "grade": grade,
        "level": level,
        "grades": grades,
        "level_choices": roles.LEVEL_CHOICES,
        "pending_count": User.objects.filter(member_level=roles.LEVEL_PENDING, is_superuser=False).count(),
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/members.html", context)


# 动作 -> (目标等级, 需要管理员, 中文名)
_LEVEL_ACTIONS = {
    "approve": (roles.LEVEL_APPLICANT, False, "通过审核（报名会员）"),
    "promote_prep": (roles.LEVEL_PREPARATORY, False, "晋升预备会员"),
    "promote_formal": (roles.LEVEL_FORMAL, False, "晋升正式会员"),
    "make_officer": (roles.LEVEL_OFFICER, True, "设为干事"),
    "make_admin": (roles.LEVEL_ADMIN, True, "设为管理员"),
    "demote_formal": (roles.LEVEL_FORMAL, True, "降为正式会员"),
}


@officer_required
@require_POST
def member_action(request):
    action = request.POST.get("action", "")
    ids = request.POST.getlist("ids")
    nxt = request.POST.get("next") or "dashboard:members"
    if not ids:
        messages.warning(request, "没有选中任何成员。")
        return redirect(nxt)

    targets = User.objects.filter(pk__in=ids, is_superuser=False).exclude(pk=request.user.pk)

    if action == "reject_delete":
        if not _is_admin(request.user):
            messages.error(request, "该操作需要管理员权限。")
            return redirect(nxt)
        count = targets.filter(member_level=roles.LEVEL_PENDING).count()
        targets.filter(member_level=roles.LEVEL_PENDING).delete()
        messages.success(request, f"已拒绝并删除 {count} 个待审核账号。")
        return redirect(nxt)

    if action == "points_adjust":
        try:
            delta = int(request.POST.get("points_delta", ""))
        except (TypeError, ValueError):
            delta = 0
        if not delta:
            messages.warning(request, "请填写非零的分值。")
            return redirect(nxt)
        note = (request.POST.get("points_note") or "").strip() or "管理组发放"
        count = 0
        for user in User.objects.filter(pk__in=ids):
            award_points(user, delta, source=PointLog.Source.ADMIN_ADJUST, note=note, operator=request.user)
            notify_user(
                user, f"积分{'+' if delta > 0 else ''}{delta}：{note}",
                kind=Notification.Kind.POINTS, url="/points/",
            )
            count += 1
        messages.success(request, f"已为 {count} 名成员调整积分 {delta:+d}。")
        return redirect(nxt)

    if action in _LEVEL_ACTIONS:
        target_level, need_admin, label = _LEVEL_ACTIONS[action]
        if need_admin and not _is_admin(request.user):
            messages.error(request, f"「{label}」需要管理员权限。")
            return redirect(nxt)
        count = 0
        for user in targets:
            user.set_level(target_level, actor=request.user, note=f"驾驶舱：{label}")
            count += 1
        messages.success(request, f"已对 {count} 名成员执行「{label}」。")
        return redirect(nxt)

    messages.error(request, "未知操作。")
    return redirect(nxt)


# ---------------------------------------------------------------- 内测反馈

@officer_required
def feedbacks(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        item = get_object_or_404(Feedback, pk=request.POST.get("id"))
        if action == "resolve":
            item.status = Feedback.Status.RESOLVED
            item.admin_note = (request.POST.get("note") or "").strip()[:200]
            item.resolved_by = request.user
            item.resolved_at = timezone.now()
            item.save(update_fields=["status", "admin_note", "resolved_by", "resolved_at"])
            notify_user(
                item.user, f"你的反馈 #{item.pk} 已处理",
                kind=Notification.Kind.FEEDBACK, body=item.admin_note,
                url=f"/feedback/{item.pk}/",
            )
            messages.success(request, f"反馈 #{item.pk} 已标记为已处理。")
        elif action == "reopen":
            item.status = Feedback.Status.PENDING
            item.save(update_fields=["status"])
            messages.success(request, f"反馈 #{item.pk} 已重新打开。")
        elif action == "delete":
            if not _is_admin(request.user):
                messages.error(request, "删除反馈需要管理员权限。")
            else:
                pk = item.pk
                item.delete()
                messages.success(request, f"反馈 #{pk} 已删除。")
        return redirect(request.POST.get("next") or "dashboard:feedbacks")

    tab = request.GET.get("tab", "pending")
    if tab not in ("pending", "all"):
        tab = "pending"
    items = Feedback.objects.select_related("user", "resolved_by").annotate(reply_count=Count("replies"))
    if tab == "pending":
        items = items.filter(status=Feedback.Status.PENDING)

    paginator = Paginator(items, 25)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "active_nav": "feedbacks",
        "tab": tab,
        "page": page,
        "pending_total": Feedback.objects.filter(status=Feedback.Status.PENDING).count(),
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/feedbacks.html", context)


# ---------------------------------------------------------------- 勋章与职位（仅管理员）

@admin_required
def medals(request):
    if request.method == "POST":
        form = request.POST.get("form")
        if form == "create_medal":
            name = request.POST.get("name", "").strip()
            if name:
                Medal.objects.get_or_create(name=name, defaults={
                    "icon": request.POST.get("icon", "🏅").strip() or "🏅",
                    "color": request.POST.get("color", "#c98a3d").strip() or "#c98a3d",
                    "description": request.POST.get("description", "").strip(),
                })
                messages.success(request, f"勋章「{name}」已创建。")
            return redirect("dashboard:medals")
        if form == "grant":
            medal = get_object_or_404(Medal, pk=request.POST.get("medal_id"))
            user = get_object_or_404(User, pk=request.POST.get("user_id"))
            reason = request.POST.get("reason", "").strip()
            _, created = UserMedal.objects.get_or_create(
                user=user, medal=medal,
                defaults={"reason": reason, "granted_by": request.user},
            )
            if created:
                notify_user(
                    user, f"你获得了勋章「{medal.icon} {medal.name}」",
                    kind=Notification.Kind.MEDAL, body=reason, url="/accounts/profile/",
                )
            messages.success(request, f"已授予 {user.display_name}「{medal.name}」。" if created else "该成员已拥有此勋章。")
            return redirect("dashboard:medals")
        if form == "delete_medal":
            medal = get_object_or_404(Medal, pk=request.POST.get("medal_id"))
            name = medal.name
            medal.delete()
            messages.success(request, f"勋章「{name}」已删除。")
            return redirect("dashboard:medals")

    context = {
        "active_nav": "medals",
        "medals": Medal.objects.annotate(holders=Count("awarded")).all(),
        "recent_grants": UserMedal.objects.select_related("user", "medal", "granted_by")[:30],
    }
    return render(request, "dashboard/medals.html", context)


@admin_required
def positions(request):
    if request.method == "POST":
        form = request.POST.get("form")
        if form == "create_position":
            name = request.POST.get("name", "").strip()
            if name:
                Position.objects.get_or_create(name=name, defaults={
                    "color": request.POST.get("color", "#b8860b").strip() or "#b8860b",
                    "sort_order": int(request.POST.get("sort_order") or 100),
                })
                messages.success(request, f"职位「{name}」已创建。")
            return redirect("dashboard:positions")
        if form == "assign":
            pos = get_object_or_404(Position, pk=request.POST.get("position_id"))
            user = get_object_or_404(User, pk=request.POST.get("user_id"))
            user.position = pos
            user.save(update_fields=["position"])
            messages.success(request, f"已任命 {user.display_name} 为「{pos.name}」。")
            return redirect("dashboard:positions")
        if form == "unassign":
            user = get_object_or_404(User, pk=request.POST.get("user_id"))
            user.position = None
            user.save(update_fields=["position"])
            messages.success(request, f"已解除 {user.display_name} 的职位。")
            return redirect("dashboard:positions")
        if form == "delete_position":
            pos = get_object_or_404(Position, pk=request.POST.get("position_id"))
            name = pos.name
            pos.delete()
            messages.success(request, f"职位「{name}」已删除。")
            return redirect("dashboard:positions")

    context = {
        "active_nav": "positions",
        "positions": Position.objects.annotate(count=Count("holders")).all(),
        "holders": User.objects.filter(position__isnull=False).select_related("position"),
    }
    return render(request, "dashboard/positions.html", context)


# ---------------------------------------------------------------- 资料管理

@officer_required
def resources(request):
    upload_form = ResourceUploadForm()
    if request.method == "POST":
        upload_form = ResourceUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            resource = upload_form.save(commit=False)
            resource.uploader = request.user
            resource.save()
            messages.success(request, f"资料「{resource.title}」上传成功。")
            return redirect("dashboard:resources")

    items = Resource.objects.select_related("uploader").order_by("-created_at")
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(title__icontains=query) | Q(description__icontains=query))
    category = request.GET.get("category", "")
    if category in Resource.Category.values:
        items = items.filter(category=category)

    paginator = Paginator(items, 20)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "active_nav": "resources",
        "page": page,
        "query": query,
        "category": category,
        "categories": Resource.Category.choices,
        "upload_form": upload_form,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/resources.html", context)


@officer_required
@require_POST
def resource_delete(request, pk: int):
    resource = get_object_or_404(Resource, pk=pk)
    if not (_is_admin(request.user) or resource.uploader_id == request.user.pk):
        messages.error(request, "只能删除自己上传的资料。")
        return redirect("dashboard:resources")
    title = resource.title
    resource.file.delete(save=False)
    resource.delete()
    messages.success(request, f"已删除资料「{title}」。")
    return redirect("dashboard:resources")


# ---------------------------------------------------------------- 公告管理

@officer_required
def news_manage(request):
    if request.method == "POST":
        item = get_object_or_404(Post, pk=request.POST.get("id"))
        action = request.POST.get("action", "")
        if action == "pin":
            item.pinned = not item.pinned
            item.save(update_fields=["pinned"])
            messages.success(request, f"「{item.title}」已{'置顶' if item.pinned else '取消置顶'}。")
        elif action == "toggle_publish":
            item.is_published = not item.is_published
            item.save(update_fields=["is_published"])
            messages.success(request, f"「{item.title}」已{'重新发布' if item.is_published else '下架'}。")
        elif action == "delete":
            if not (_is_admin(request.user) or item.author_id == request.user.pk):
                messages.error(request, "只能删除自己发布的公告（或需要管理员权限）。")
            else:
                title = item.title
                if item.cover:
                    item.cover.delete(save=False)
                item.delete()
                messages.success(request, f"公告「{title}」已删除。")
        return redirect(request.POST.get("next") or "dashboard:news")

    items = Post.objects.select_related("author")
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(title__icontains=query) | Q(body__icontains=query))
    category = request.GET.get("category", "")
    if category in Post.Category.values:
        items = items.filter(category=category)

    paginator = Paginator(items, 20)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "active_nav": "news",
        "page": page,
        "query": query,
        "category": category,
        "categories": Post.Category.choices,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/news.html", context)


@officer_required
def news_edit(request, pk: int | None = None):
    post = get_object_or_404(Post, pk=pk) if pk else None

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            item = form.save(commit=False)
            if item.author_id is None:
                item.author = request.user
            item.save()
            messages.success(request, f"公告「{item.title}」已{'更新' if pk else '发布'}。")
            return redirect("dashboard:news")
    else:
        form = PostForm(instance=post)

    context = {
        "active_nav": "news",
        "form": form,
        "post": post,
    }
    return render(request, "dashboard/news_form.html", context)


_INLINE_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}


@officer_required
@require_POST
def inline_image_upload(request):
    """正文配图上传（公告/活动共用，AJAX），返回可直接插入 Markdown 的 URL。"""
    from django.core.files.storage import default_storage
    from django.http import JsonResponse
    from django.utils import timezone as tz

    file = request.FILES.get("image")
    if not file:
        return JsonResponse({"ok": False, "msg": "没有收到图片。"}, status=400)
    ext = _INLINE_IMAGE_TYPES.get(file.content_type)
    if not ext:
        return JsonResponse({"ok": False, "msg": "仅支持 JPG / PNG / GIF / WebP 图片。"}, status=400)
    if file.size > 10 * 1024 * 1024:
        return JsonResponse({"ok": False, "msg": "图片超过 10MB，请压缩后再传。"}, status=400)

    name = f"uploads/inline/{tz.now():%Y/%m}/{uuid.uuid4().hex[:12]}{ext}"
    saved = default_storage.save(name, file)
    return JsonResponse({"ok": True, "url": default_storage.url(saved)})


# ---------------------------------------------------------------- 活动管理

@officer_required
def events_manage(request):
    if request.method == "POST":
        item = get_object_or_404(Event, pk=request.POST.get("id"))
        action = request.POST.get("action", "")
        if action == "toggle_publish":
            item.is_published = not item.is_published
            item.save(update_fields=["is_published"])
            messages.success(request, f"「{item.title}」已{'发布' if item.is_published else '下架'}。")
        elif action == "open_checkin":
            code = item.open_checkin()
            messages.success(request, f"「{item.title}」签到已开启，口令：{code}")
        elif action == "close_checkin":
            item.close_checkin()
            messages.success(request, f"「{item.title}」签到已关闭。")
        elif action == "delete":
            if not (_is_admin(request.user) or item.created_by_id == request.user.pk):
                messages.error(request, "只能删除自己发布的活动（或需要管理员权限）。")
            else:
                title = item.title
                item.delete()
                messages.success(request, f"活动「{title}」已删除。")
        return redirect(request.POST.get("next") or "dashboard:events")

    items = Event.objects.select_related("created_by").annotate(
        signup_total=Count("signups"),
        checkin_total=Count("signups", filter=Q(signups__checkin_at__isnull=False)),
    )
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(title__icontains=query) | Q(location__icontains=query))

    paginator = Paginator(items, 20)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "active_nav": "events",
        "page": page,
        "query": query,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/events.html", context)


@officer_required
def event_edit(request, pk: int | None = None):
    event = get_object_or_404(Event, pk=pk) if pk else None

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            item = form.save(commit=False)
            if item.created_by_id is None:
                item.created_by = request.user
            item.save()
            messages.success(request, f"活动「{item.title}」已{'更新' if pk else '创建'}。")
            return redirect("dashboard:events")
    else:
        form = EventForm(instance=event)

    context = {
        "active_nav": "events",
        "form": form,
        "event": event,
    }
    return render(request, "dashboard/event_form.html", context)


@officer_required
def event_signups(request, pk: int):
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST" and request.POST.get("action") == "manual_checkin":
        # 现场兜底：工作人员替没带手机的成员手动签到
        signup = get_object_or_404(EventSignup, pk=request.POST.get("signup_id"), event=event)
        if not signup.checked_in:
            signup.checkin_at = timezone.now()
            signup.save(update_fields=["checkin_at"])
            if event.points_reward:
                award_points(
                    signup.user, event.points_reward,
                    source=PointLog.Source.EVENT_CHECKIN,
                    note=f"活动签到（工作人员代签）：{event.title}", operator=request.user,
                )
            messages.success(request, f"已为 {signup.user.display_name} 手动签到。")
        return redirect("dashboard:event_signups", pk=event.pk)

    signups = event.signups.select_related("user", "user__position").order_by("created_at")

    if request.GET.get("export") == "csv":
        import csv

        from django.http import HttpResponse
        from urllib.parse import quote

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        filename = quote(f"{event.title}-报名名单.csv")
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
        writer = csv.writer(response)
        writer.writerow(["姓名", "用户名", "学号", "学院", "年级", "等级", "报名时间", "签到时间", "现场参加"])
        for s in signups:
            writer.writerow([
                s.user.real_name, s.user.username, s.user.student_id, s.user.college,
                s.user.grade, s.user.level_label,
                s.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                s.checkin_at.astimezone().strftime("%Y-%m-%d %H:%M") if s.checkin_at else "",
                "是" if s.is_walkin else "",
            ])
        return response

    context = {
        "active_nav": "events",
        "event": event,
        "signups": signups,
        "signup_total": signups.count(),
        "checkin_total": signups.filter(checkin_at__isnull=False).count(),
    }
    return render(request, "dashboard/event_signups.html", context)


@officer_required
def event_checkin_qr(request, pk: int):
    """签到二维码：扫码直达活动页并自动填入口令。"""
    import io

    import qrcode
    from django.http import HttpResponse

    event = get_object_or_404(Event, pk=pk)
    if not event.checkin_code:
        from django.http import Http404

        raise Http404("尚未开启签到")

    url = request.build_absolute_uri(f"/events/{event.pk}/?code={event.checkin_code}")
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


# ---------------------------------------------------------------- 招新管理

# 面试结果动作 -> (报名状态, 目标等级或 None, 中文说明)
_RECRUIT_RESULTS = {
    "first_pass": (Application.Status.FIRST_PASS, roles.LEVEL_PREPARATORY, "一面通过 · 晋升预备会员"),
    "second_pass": (Application.Status.SECOND_PASS, roles.LEVEL_FORMAL, "二面通过 · 晋升正式会员"),
    "reject": (Application.Status.REJECTED, None, "本次未录取"),
    "reset": (Application.Status.SUBMITTED, None, "重置为已报名"),
}


def _apply_recruit_result(application, key: str, note: str, actor) -> None:
    status, level, label = _RECRUIT_RESULTS[key]
    application.status = status
    if note:
        application.interview_note = note[:300]
    application.save(update_fields=["status", "interview_note", "updated_at"])
    if level is not None:
        # set_level 内部写 LevelLog、同步论坛组、发等级变更站内通知
        application.user.set_level(level, actor=actor, note=f"招新：{label}")
    elif status == Application.Status.REJECTED:
        notify_user(
            application.user, "招新结果通知",
            kind=Notification.Kind.LEVEL,
            body="很遗憾本次未能录取。欢迎继续参加培训和活动，期待下次与你相遇！",
            url="/recruitment/",
        )


@officer_required
def recruitment_manage(request):
    campaigns = list(Campaign.objects.all())

    cid = request.GET.get("campaign")
    campaign = None
    if cid and cid.isdigit():
        campaign = next((c for c in campaigns if c.pk == int(cid)), None)
    if campaign is None and campaigns:
        campaign = campaigns[0]

    if request.method == "POST":
        nxt = request.POST.get("next") or "dashboard:recruitment"
        if request.POST.get("action") == "set_result":
            key = request.POST.get("result", "")
            note = (request.POST.get("note") or "").strip()
            ids = request.POST.getlist("ids")
            if key not in _RECRUIT_RESULTS:
                messages.error(request, "未知操作。")
                return redirect(nxt)
            apps = Application.objects.select_related("user").filter(pk__in=ids)
            count = 0
            for application in apps:
                _apply_recruit_result(application, key, note, request.user)
                count += 1
            if count:
                messages.success(request, f"已更新 {count} 名报名者：{_RECRUIT_RESULTS[key][2]}。")
            else:
                messages.warning(request, "没有选中任何报名者。")
        return redirect(nxt)

    status = request.GET.get("status", "")
    applications = []
    status_tabs = []
    total_count = 0
    if campaign:
        base = campaign.applications.select_related("user", "user__position")
        counts = {row["status"]: row["c"] for row in base.values("status").annotate(c=Count("id"))}
        total_count = sum(counts.values())
        status_tabs = [(value, label, counts.get(value, 0)) for value, label in Application.Status.choices]
        applications = base if status not in Application.Status.values else base.filter(status=status)

        if request.GET.get("export") == "csv":
            import csv
            from urllib.parse import quote

            from django.http import HttpResponse

            response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
            filename = quote(f"{campaign.name}-报名名单.csv")
            response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
            writer = csv.writer(response)
            writer.writerow(["姓名", "用户名", "学号", "学院", "年级", "意向部门", "特长", "进展", "面试备注", "报名时间"])
            for a in applications:
                writer.writerow([
                    a.user.real_name, a.user.username, a.user.student_id, a.user.college, a.user.grade,
                    a.get_department_display(), a.skills, a.get_status_display(),
                    a.interview_note, a.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                ])
            return response

    context = {
        "active_nav": "recruitment",
        "campaigns": campaigns,
        "campaign": campaign,
        "applications": applications,
        "status": status,
        "status_tabs": status_tabs,
        "total_count": total_count,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/recruitment.html", context)


@officer_required
def campaign_edit(request, pk: int | None = None):
    campaign = get_object_or_404(Campaign, pk=pk) if pk else None

    if request.method == "POST":
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            item = form.save()
            messages.success(request, f"招新批次「{item.name}」已{'更新' if pk else '创建'}。")
            return redirect(f"{reverse('dashboard:recruitment')}?campaign={item.pk}")
    else:
        form = CampaignForm(instance=campaign)

    context = {"active_nav": "recruitment", "form": form, "campaign": campaign}
    return render(request, "dashboard/campaign_form.html", context)


# ---------------------------------------------------------------- 项目档案管理

@officer_required
def projects_manage(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        project = get_object_or_404(Project, pk=request.POST.get("id"))
        if action == "archive":
            project.status = Project.Status.ARCHIVED
            project.save(update_fields=["status", "updated_at"])
            messages.success(request, f"项目「{project.name}」已归档。")
        elif action == "activate":
            project.status = Project.Status.ACTIVE
            project.save(update_fields=["status", "updated_at"])
            messages.success(request, f"项目「{project.name}」已恢复为进行中。")
        elif action == "delete":
            if not _is_admin(request.user):
                messages.error(request, "删除项目需要管理员权限。")
            else:
                name = project.name
                for f in project.files.all():
                    f.file.delete(save=False)
                project.delete()
                messages.success(request, f"项目「{name}」及其文件已删除。")
        return redirect(request.POST.get("next") or "dashboard:projects")

    items = Project.objects.select_related("created_by").annotate(
        member_total=Count("members", distinct=True),
        file_total=Count("files", distinct=True),
    )
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(name__icontains=query) | Q(summary__icontains=query))

    paginator = Paginator(items, 20)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "active_nav": "projects",
        "page": page,
        "query": query,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/projects.html", context)


@officer_required
def project_edit(request, pk: int | None = None):
    project = get_object_or_404(Project, pk=pk) if pk else None

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        lead_name = (request.POST.get("lead") or "").strip()
        if form.is_valid():
            item = form.save(commit=False)
            if item.created_by_id is None:
                item.created_by = request.user
            item.save()
            # 指派负责人（用用户名或学号）
            if lead_name:
                lead = User.objects.filter(username=lead_name).first() or \
                    User.objects.filter(student_id=lead_name).first()
                if lead is None:
                    messages.warning(request, f"项目已保存，但没找到负责人「{lead_name}」，请到项目页手动指派。")
                else:
                    ProjectMember.objects.update_or_create(
                        project=item, user=lead, defaults={"role": ProjectMember.Role.LEAD},
                    )
            messages.success(request, f"项目「{item.name}」已{'更新' if pk else '创建'}。")
            return redirect("dashboard:projects")
    else:
        form = ProjectForm(instance=project)

    context = {"active_nav": "projects", "form": form, "project": project}
    return render(request, "dashboard/project_form.html", context)


# ---------------------------------------------------------------- 站点设置（仅管理员）

@admin_required
def site_settings(request):
    config = SiteConfig.load()

    config_form = SiteConfigForm(instance=config)
    carousel_form = CarouselImageForm()

    if request.method == "POST":
        form_name = request.POST.get("form")
        if form_name == "config":
            config_form = SiteConfigForm(request.POST, instance=config)
            if config_form.is_valid():
                config_form.save()
                messages.success(request, "站点配置已保存。")
                return redirect("dashboard:site_settings")
        elif form_name == "carousel_add":
            carousel_form = CarouselImageForm(request.POST, request.FILES)
            if carousel_form.is_valid():
                carousel_form.save()
                messages.success(request, "轮播图已添加。")
                return redirect("dashboard:site_settings")

    context = {
        "active_nav": "site",
        "config_form": config_form,
        "carousel_form": carousel_form,
        "carousel_items": CarouselImage.objects.all(),
    }
    return render(request, "dashboard/site_settings.html", context)


@admin_required
@require_POST
def carousel_update(request, pk: int):
    item = get_object_or_404(CarouselImage, pk=pk)
    action = request.POST.get("action")
    if action == "toggle":
        item.is_active = not item.is_active
        item.save(update_fields=["is_active"])
        messages.success(request, f"「{item.title}」已{'启用' if item.is_active else '停用'}。")
    elif action == "delete":
        title = item.title
        item.image.delete(save=False)
        item.delete()
        messages.success(request, f"轮播图「{title}」已删除。")
    elif action == "sort":
        try:
            item.sort_order = int(request.POST.get("sort_order", item.sort_order))
            item.save(update_fields=["sort_order"])
            messages.success(request, f"「{item.title}」排序已更新。")
        except (TypeError, ValueError):
            messages.error(request, "排序值无效。")
    return redirect("dashboard:site_settings")
