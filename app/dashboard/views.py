import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts import roles
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
    pending_count = User.objects.filter(is_active=False, is_superuser=False).count()
    officer_count = User.objects.filter(
        Q(groups__name__in=[roles.GROUP_OFFICER, roles.GROUP_ADMIN]) | Q(is_staff=True), is_active=True
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
        tab = "pending" if User.objects.filter(is_active=False, is_superuser=False).exists() else "all"

    users = User.objects.prefetch_related("groups").order_by("-date_joined")
    if tab == "pending":
        users = users.filter(is_active=False, is_superuser=False)

    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(username__icontains=query) | Q(real_name__icontains=query)
            | Q(student_id__icontains=query) | Q(qq__icontains=query)
            | Q(college__icontains=query)
        )

    grade = request.GET.get("grade", "").strip()
    if grade:
        users = users.filter(grade=grade)

    role = request.GET.get("role", "")
    if role == "member":
        users = users.filter(groups__name=roles.GROUP_MEMBER)
    elif role == "officer":
        users = users.filter(Q(groups__name__in=[roles.GROUP_OFFICER, roles.GROUP_ADMIN]) | Q(is_staff=True))

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
        "role": role,
        "grades": grades,
        "pending_count": User.objects.filter(is_active=False, is_superuser=False).count(),
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/members.html", context)


@officer_required
@require_POST
def member_action(request):
    action = request.POST.get("action", "")
    ids = request.POST.getlist("ids")
    if not ids:
        messages.warning(request, "没有选中任何成员。")
        return redirect(request.POST.get("next") or "dashboard:members")

    admin_actions = {"reject_delete", "make_officer", "remove_officer"}
    if action in admin_actions and not _is_admin(request.user):
        messages.error(request, "该操作需要管理员权限。")
        return redirect(request.POST.get("next") or "dashboard:members")

    targets = User.objects.filter(pk__in=ids, is_superuser=False).exclude(pk=request.user.pk)
    member_group = Group.objects.get(name=roles.GROUP_MEMBER)
    officer_group = Group.objects.get(name=roles.GROUP_OFFICER)

    count = 0
    if action == "approve":
        for user in targets.filter(is_active=False):
            user.is_active = True
            user.save(update_fields=["is_active"])
            user.groups.add(member_group)
            count += 1
        messages.success(request, f"已通过 {count} 名成员的审核。")
    elif action == "reject_delete":
        count = targets.filter(is_active=False).count()
        targets.filter(is_active=False).delete()
        messages.success(request, f"已拒绝并删除 {count} 个待审核账号。")
    elif action == "make_officer":
        for user in targets.filter(is_active=True):
            user.groups.add(officer_group, member_group)
            count += 1
        messages.success(request, f"已将 {count} 名成员设为干事。")
    elif action == "remove_officer":
        for user in targets:
            user.groups.remove(officer_group)
            count += 1
        messages.success(request, f"已取消 {count} 名成员的干事身份。")
    else:
        messages.error(request, "未知操作。")

    return redirect(request.POST.get("next") or "dashboard:members")


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
