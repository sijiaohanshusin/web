import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.models import Medal, Position, UserMedal
from core import bilibili
from core.models import CarouselImage, SiteConfig
from files.forms import ResourceUploadForm
from files.models import Resource

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
                    "color": request.POST.get("color", "#f59e0b").strip() or "#f59e0b",
                    "description": request.POST.get("description", "").strip(),
                })
                messages.success(request, f"勋章「{name}」已创建。")
            return redirect("dashboard:medals")
        if form == "grant":
            medal = get_object_or_404(Medal, pk=request.POST.get("medal_id"))
            user = get_object_or_404(User, pk=request.POST.get("user_id"))
            _, created = UserMedal.objects.get_or_create(
                user=user, medal=medal,
                defaults={"reason": request.POST.get("reason", "").strip(), "granted_by": request.user},
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
