import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

import re
import uuid
from pathlib import Path

from accounts import roles
from accounts.choices import COLLEGE_CHOICES, cohort_choices, position_term_choices
from accounts.models import Medal, Position, PositionAppointment, ReturningMembershipRequest, UserMedal
from core import bilibili
from core import slots as slot_registry
from core.models import CarouselImage, Feedback, MediaSlot, SiteConfig
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
from .forms import CarouselImageForm, MediaSlotForm, SiteConfigForm
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

    total_members = User.objects.filter(is_active=True, member_level__gte=roles.LEVEL_PREPARATORY).count()
    pending_count = ReturningMembershipRequest.objects.filter(
        status=ReturningMembershipRequest.Status.PENDING,
    ).count()
    officer_count = User.objects.filter(
        Q(member_level__gte=roles.LEVEL_OFFICER) | Q(is_staff=True)
        | Q(position__grants_management=True),
        is_active=True,
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
    if tab not in ("returning", "recruits", "all"):
        tab = "returning" if ReturningMembershipRequest.objects.filter(
            status=ReturningMembershipRequest.Status.PENDING,
        ).exists() else "recruits"

    users = User.objects.select_related("position", "returning_request").annotate(
        medal_count=Count("medals"),
    ).order_by("-date_joined")
    if tab == "returning":
        users = users.filter(returning_request__isnull=False, is_superuser=False)
    elif tab == "recruits":
        users = users.filter(member_level=roles.LEVEL_APPLICANT, is_active=True, is_superuser=False)

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
        "pending_count": ReturningMembershipRequest.objects.filter(
            status=ReturningMembershipRequest.Status.PENDING,
        ).count(),
        "returning_role_choices": ReturningMembershipRequest.RequestedRole.choices,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/members.html", context)


# 动作 -> (目标等级, 需要管理员, 中文名)
_LEVEL_ACTIONS = {
    "promote_prep": (roles.LEVEL_PREPARATORY, False, "晋升预备会员"),
    "promote_formal": (roles.LEVEL_FORMAL, False, "晋升科协会员"),
    "make_officer": (roles.LEVEL_OFFICER, True, "设为站务管理"),
    "make_admin": (roles.LEVEL_ADMIN, True, "设为系统管理员"),
    "demote_formal": (roles.LEVEL_FORMAL, True, "调整为科协会员"),
}


@officer_required
@require_POST
@transaction.atomic
def member_action(request):
    action = request.POST.get("action", "")
    ids = request.POST.getlist("ids")
    nxt = request.POST.get("next") or reverse("dashboard:members")
    if not url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        nxt = reverse("dashboard:members")
    if any(not value.isascii() or not value.isdecimal() or len(value) > 18 for value in ids):
        messages.error(request, "成员选择无效，请重新选择列表中的成员。")
        return redirect(nxt)
    if not ids:
        messages.warning(request, "没有选中任何成员。")
        return redirect(nxt)

    targets = User.objects.filter(pk__in=ids, is_superuser=False).exclude(pk=request.user.pk)

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
        count = skipped = 0
        for user in targets.select_for_update().order_by("pk"):
            # Promotion is never a demotion, and officers cannot alter privileged accounts.
            if (action.startswith("promote_") and user.member_level >= target_level) or (
                not _is_admin(request.user) and (user.is_staff or roles.is_officer(user))
            ):
                skipped += 1
                continue
            user.set_level(target_level, actor=request.user, note=f"驾驶舱：{label}")
            count += 1
        if skipped:
            messages.warning(request, f"已跳过 {skipped} 名无需晋升或需要系统管理员处理的成员。")
        messages.success(request, f"已对 {count} 名成员执行「{label}」。")
        return redirect(nxt)

    messages.error(request, "未知操作。")
    return redirect(nxt)


_RETURNING_POSITIONS = {
    ReturningMembershipRequest.RequestedRole.CHAIR: ("主席", "#b8860b", True, 10),
    ReturningMembershipRequest.RequestedRole.HARDWARE_CHAIR: ("硬件主席", "#c98a3d", True, 20),
    ReturningMembershipRequest.RequestedRole.SOFTWARE_CHAIR: ("软件主席", "#0da9cd", True, 30),
    ReturningMembershipRequest.RequestedRole.HARDWARE_VICE_CHAIR: ("硬件副主席", "#d97706", False, 40),
    ReturningMembershipRequest.RequestedRole.SOFTWARE_VICE_CHAIR: ("软件副主席", "#0284c7", False, 50),
}


@officer_required
@require_POST
def returning_review(request, pk: int):
    item = get_object_or_404(ReturningMembershipRequest.objects.select_related("user"), pk=pk)
    decision = request.POST.get("decision")
    note = (request.POST.get("note") or "").strip()[:200]

    if decision == "reject":
        item.user.is_active = False
        item.user.position = None
        item.user._position_operator = request.user
        item.user.save(update_fields=["is_active", "position"])
        item.mark_reviewed(ReturningMembershipRequest.Status.REJECTED, request.user, note)
        messages.success(request, f"已拒绝 {item.user.display_name} 的身份恢复申请，记录已保留。")
        return redirect("dashboard:members")

    role = request.POST.get("role")
    if role not in ReturningMembershipRequest.RequestedRole.values:
        messages.error(request, "请选择有效的协会身份。")
        return redirect("dashboard:members")

    item.requested_role = role
    position = None
    if role in _RETURNING_POSITIONS:
        name, color, grants_management, sort_order = _RETURNING_POSITIONS[role]
        position, _ = Position.objects.update_or_create(
            name=name,
            defaults={
                "color": color,
                "grants_management": grants_management,
                "sort_order": sort_order,
            },
        )

    user = item.user
    user.position = position
    user._position_operator = request.user
    user.member_level = roles.LEVEL_FORMAL
    user.is_active = True
    user.save(update_fields=["position", "member_level", "is_active"])
    roles.sync_user_groups(user)
    item.mark_reviewed(ReturningMembershipRequest.Status.APPROVED, request.user, note)
    item.save(update_fields=["requested_role"])

    try:
        send_mail(
            "HEU ESTA 老会员身份审核通过",
            f"{user.display_name}，你的老会员身份已审核通过，现可登录协会网站。",
            None,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        messages.warning(request, "身份已通过，但审核结果邮件发送失败，请通过 QQ 联系对方。")
    messages.success(request, f"已恢复 {user.display_name} 的{item.get_requested_role_display()}身份。")
    return redirect("dashboard:members")


# ---------------------------------------------------------------- 网站问题反馈

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
    items = Feedback.objects.select_related("user", "resolved_by").annotate(
        reply_count=Count("replies"),
    ).order_by("-created_at")
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
    grant_values = {}
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
            grant_values = {
                field: request.POST.get(field, "").strip()
                for field in ("medal_id", "user_id", "reason")
            }
            medal = Medal.objects.filter(pk=_form_pk(grant_values["medal_id"])).first()
            user = _resolve_member(request, grant_values["user_id"])
            reason = grant_values["reason"]
            if medal is None:
                messages.error(request, "请选择仍然存在的勋章；勋章可能已被其他管理员删除。")
            if len(reason) > 200:
                messages.error(request, "授予理由不能超过 200 字，请缩短后重试。")
            if medal is not None and user is not None and len(reason) <= 200:
                with transaction.atomic():
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
        "grant_values": grant_values,
        # order_by 必须显式写：`annotate()` 会建 GROUP BY，而带 GROUP BY 的查询
        # **不再套用 Meta.ordering**（生成的 SQL 里压根没有 ORDER BY），于是列表
        # 变成数据库返回的任意顺序，页面照常渲染、没有任何报错。
        "medals": Medal.objects.annotate(holders=Count("awarded")).order_by("sort_order", "id"),
        "recent_grants": UserMedal.objects.select_related("user", "medal", "granted_by")[:30],
    }
    return render(request, "dashboard/medals.html", context)


def _fixed_position_names() -> set[str]:
    """老会员通道审核时会 `update_or_create` 的五个职位名。

    这五个不能改名、不能删：`returning_review()` 按**名字**去建它们，改掉名字之后
    下一次审核会静默再建一个同义的新职位，于是同一个「硬件主席」在库里有两条、
    团队页上出现两个分组。所以这里把它们标成固定项，驾驶舱只允许改颜色和简介。
    """
    return {item[0] for item in _RETURNING_POSITIONS.values()}


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _clean_hex(value: str, fallback: str) -> str:
    """职位颜色会直接进模板的 style 属性，只放行标准六位十六进制值。"""
    value = (value or "").strip()
    return value if _HEX_COLOR.match(value) else fallback


def _form_pk(raw: str) -> int | None:
    """Validate posted IDs before they reach the database's integer field."""
    value = (raw or "").strip()
    return int(value) if re.fullmatch(r"[0-9]{1,18}", value) else None


def _resolve_member(request, raw: str, what: str = "成员"):
    """Resolve typed member identities without losing form input or guessing names."""
    hits = User.find_by_identifier(raw)
    if len(hits) == 1:
        return hits[0]

    raw = (raw or "").strip()
    if not raw:
        messages.error(request, f"请填写要操作的{what}（用户名 / 学号 / 姓名）。")
    elif not hits:
        messages.error(
            request,
            f"没找到{what}「{raw}」。可以填用户名、学号或姓名 —— "
            "在「会员管理」页能搜到；也可以用「现任职成员」表里那个 #ID。",
        )
    else:
        who = "、".join(
            f"{u.display_name}（@{u.username}"
            + (f" · 学号 {u.student_id}" if u.student_id else "")
            + "）"
            for u in hits
        )
        messages.error(
            request,
            f"有 {len(hits)} 个人叫「{raw}」，认不准是哪一位，请改用用户名或学号：{who}",
        )
    return None


@never_cache
@admin_required
@require_GET
def position_members(request):
    query = request.GET.get("q", "").strip()
    grade = request.GET.get("grade", "")
    college = request.GET.get("college", "")
    position = request.GET.get("position", "")
    if (
        len(query) > 150
        or (grade and grade not in dict(cohort_choices()))
        or (college and college not in dict(COLLEGE_CHOICES))
        or (position and position != "unassigned" and not _form_pk(position))
    ):
        return JsonResponse({"error": "筛选条件无效，请重新选择。"}, status=400)

    members = User.objects.select_related("position")
    if query.startswith("#"):
        members = members.filter(pk=_form_pk(query[1:]))
    elif query.startswith("@"):
        members = members.filter(username__icontains=query[1:])
    elif query:
        members = members.filter(
            Q(real_name__icontains=query) | Q(username__icontains=query) | Q(student_id__icontains=query)
        )
    if grade:
        members = members.filter(grade=grade)
    if college:
        members = members.filter(college=college)
    if position == "unassigned":
        members = members.filter(position__isnull=True)
    elif position:
        members = members.filter(position_id=_form_pk(position))

    # Bound each response; only return fields needed to distinguish candidates.
    rows = list(members.order_by("-is_active", "real_name", "username", "pk")[:13])
    return JsonResponse({
        "members": [
            {
                "id": member.pk,
                "username": member.username,
                "name": member.display_name,
                "student_id": member.student_id,
                "grade": member.grade,
                "college": member.college,
                "position": member.position.name if member.position_id else "",
                "term": member.position_term_label if member.position_id else "",
                "is_active": member.is_active,
            }
            for member in rows[:12]
        ],
        "has_more": len(rows) > 12,
    })


@admin_required
def positions(request):
    fixed_names = _fixed_position_names()

    if request.method == "POST":
        form = request.POST.get("form")

        if form == "create":
            name = (request.POST.get("name") or "").strip()[:30]
            if not name:
                messages.error(request, "请填写职位名称。")
            elif Position.objects.filter(name=name).exists():
                messages.error(request, f"职位「{name}」已存在。")
            else:
                Position.objects.create(
                    name=name,
                    color=_clean_hex(request.POST.get("color"), "#0da9cd"),
                    blurb=(request.POST.get("blurb") or "").strip()[:80],
                    sort_order=int(request.POST.get("sort_order") or 100),
                    # **自定义职位永不授予驾驶舱权限。** 需要站务权限就直接把等级
                    # 提到「站务管理」，那条路有日志、有通知、有审计。把它做成这一页
                    # 上的一个复选框等于多开一条没人盯着的提权入口。
                    grants_management=False,
                )
                messages.success(request, f"职位「{name}」已创建。可以任命成员了。")
            return redirect("dashboard:positions")

        if form == "update":
            pos = get_object_or_404(Position, pk=request.POST.get("position_id"))
            pos.color = _clean_hex(request.POST.get("color"), pos.color)
            pos.blurb = (request.POST.get("blurb") or "").strip()[:80]
            pos.sort_order = int(request.POST.get("sort_order") or pos.sort_order)
            pos.save(update_fields=["color", "blurb", "sort_order"])
            messages.success(request, f"职位「{pos.name}」已更新。")
            return redirect("dashboard:positions")

        if form == "delete":
            pos = get_object_or_404(Position, pk=request.POST.get("position_id"))
            if pos.name in fixed_names:
                messages.error(request, f"「{pos.name}」是固定职位，不能删除。")
            else:
                # SET_NULL：在任的人只是失去职位，账号和等级不动
                name, count = pos.name, pos.holders.count()
                pos.delete()
                messages.success(
                    request,
                    f"职位「{name}」已删除。" + (f"{count} 位在任成员的职位已清空。" if count else ""),
                )
            return redirect("dashboard:positions")

        if form == "assign":
            # 职位来自服务端渲染的 <select>，成员是人手打的 —— 两者的失败方式不同，
            # 所以分开处理：职位对不上是「刚被别人删了」，成员对不上是「填了个别的
            # 标识」，后者必须留在这一页上说清楚，不能 404 把填的东西全丢掉。
            pos = Position.objects.filter(pk=_form_pk(request.POST.get("position_id"))).first()
            user = _resolve_member(request, request.POST.get("user_id")) if pos else None
            term_raw = request.POST.get("term_start", "")
            term = _form_pk(term_raw) if term_raw else None
            status = request.POST.get("appointment_status", "current")
            valid_term = not term_raw or term in dict(position_term_choices())
            if pos is None:
                messages.error(request, "请选择职位（也可能是它刚被删掉了，刷新一下）。")
            elif not valid_term or (status == "history" and term is None):
                messages.error(request, "请选择有效的任职届次；历任补录必须注明届次。")
            elif status not in ("current", "history"):
                messages.error(request, "请选择现任任命或历任补录。")
            elif user is not None:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=user.pk)
                    if status == "history":
                        if PositionAppointment.objects.filter(user=user, position_name=pos.name, term_start=term).exists():
                            messages.info(request, "该成员在此届次的职位记录已存在，未重复添加。")
                        else:
                            PositionAppointment.objects.create(
                                user=user, position=pos, position_name=pos.name, term_start=term,
                                ended_at=timezone.now(), operator=request.user,
                            )
                            messages.success(request, "历任记录已补充，不改变现任职位、会员等级或管理权限。")
                        return redirect("dashboard:positions")
                    user.position = pos
                    user.position_term_start = term
                    user._position_operator = request.user
                    user.save(update_fields=["position", "position_term_start"])
                messages.success(
                    request,
                    f"已任命 {user.display_name} 为「{pos.name}」。"
                    "公开展示需本人进入「个人中心 → 编辑资料 → 公开团队页」勾选并保存。",
                )
                if not user.is_active:
                    messages.warning(
                        request,
                        f"注意：{user.display_name} 的账号当前是停用状态，"
                        "停用期间不会出现在公开团队页上。",
                    )
                return redirect("dashboard:positions")

        if form == "unassign":
            # Hidden IDs must not resolve to another person's numeric username/student ID.
            raw_id = (request.POST.get("user_id") or "").strip().removeprefix("#")
            user = User.objects.filter(pk=_form_pk(raw_id)).first()
            if user is not None:
                user.position = None
                user._position_operator = request.user
                user.save(update_fields=["position"])
                messages.success(request, f"已将 {user.display_name} 标为卸任，历任记录已保留。")
            else:
                messages.error(request, "未找到要解除职位的成员，请刷新页面后重试。")
            return redirect("dashboard:positions")

    # order_by 必须显式写：`annotate()` 建了 GROUP BY，带 GROUP BY 的查询不再套用
    # Meta.ordering（SQL 里压根没有 ORDER BY）。这一页尤其明显 —— 职位顺序就是
    # 团队页上的卡片顺序，乱了就是主席排在干事后面，而且不报错。
    all_positions = list(
        Position.objects.annotate(count=Count("holders")).order_by("sort_order", "id")
    )
    for pos in all_positions:
        pos.is_fixed = pos.name in fixed_names

    holders = User.objects.filter(position__isnull=False).select_related("position")
    history_query = request.GET.get("history_q", "").strip()[:150]
    history_term = request.GET.get("history_term", "")
    history = PositionAppointment.objects.filter(ended_at__isnull=False).select_related("user")
    if history_query:
        history = history.filter(
            Q(user__username__icontains=history_query) | Q(user__real_name__icontains=history_query)
            | Q(user__student_id__icontains=history_query) | Q(position_name__icontains=history_query)
        )
    if history_term:
        history = history.filter(term_start=_form_pk(history_term)) if _form_pk(history_term) else history.none()

    context = {
        "active_nav": "positions",
        "positions": all_positions,
        "holders": holders,
        "grade_choices": cohort_choices(),
        "college_choices": COLLEGE_CHOICES,
        "term_choices": position_term_choices(),
        "assignment_term": request.POST.get("term_start", str(timezone.localdate().year)),
        "assignment_status": request.POST.get("appointment_status", "current"),
        "history": Paginator(history, 20).get_page(request.GET.get("history_page")),
        "history_query": history_query,
        "history_term": history_term,
        "assignment_value": request.POST.get("user_id", "") if request.POST.get("form") == "assign" else "",
        "assignment_position": request.POST.get("position_id", "") if request.POST.get("form") == "assign" else "",
        # 任命 ≠ 上墙。没有这个数字，站务任命完只会以为团队页坏了。
        "awaiting_optin": sum(1 for u in holders if not u.showcase_is_public),
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

    # order_by 显式写：annotate() 的 GROUP BY 会让 Meta.ordering 失效，而这个列表
    # 还要分页 —— 无序查询分页会让同一条记录在两页里重复出现或者干脆消失
    items = Event.objects.select_related("created_by").annotate(
        signup_total=Count("signups"),
        checkin_total=Count("signups", filter=Q(signups__checkin_at__isnull=False)),
    ).order_by("-start_at")
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

# 报名名单 CSV 的列。**一个列表同时定义表头与取值**，不写成两份平行的列表 ——
# 那样加一列时很容易只改一处，结果整份 CSV 从那一列起全部错位一格，而文件照常
# 打开、Excel 里也不报错。测试里有一条断言表头长度 == 数据行长度。
#
# 口径是纸质《会员申请表》：站务拿这份当打印底稿（线下仍然签纸质表）。
# 两组多选走 `interests_display` / `channels_display` —— 它们已经把「其他」的补充
# 接在后面了，所以不再单开「其他方向」「其他渠道」两列。
_APPLICATION_CSV_COLUMNS = (
    ("姓名", lambda a: a.user.real_name),
    ("用户名", lambda a: a.user.username),
    ("学号", lambda a: a.user.student_id),
    ("学院", lambda a: a.user.college),
    ("年级", lambda a: a.user.grade),
    ("性别", lambda a: a.user.get_gender_display()),
    ("出生日期", lambda a: a.user.birthday.strftime("%Y-%m-%d") if a.user.birthday else ""),
    ("手机", lambda a: a.user.phone),
    ("QQ", lambda a: a.user.qq),
    ("邮箱", lambda a: a.user.email),
    ("意向部门", lambda a: a.get_department_display()),
    ("兴趣方向", lambda a: a.interests_display),
    ("主要经历 / 兴趣爱好", lambda a: a.skills),
    ("自我介绍", lambda a: a.self_intro),
    ("对协会的初步印象", lambda a: a.first_impression),
    ("对大学四年的寄语", lambda a: a.motto),
    ("得知渠道", lambda a: a.channels_display),
    ("进展", lambda a: a.get_status_display()),
    ("面试备注", lambda a: a.interview_note),
    ("报名时间", lambda a: a.created_at.astimezone().strftime("%Y-%m-%d %H:%M")),
)


# 面试结果动作 -> (报名状态, 目标等级或 None, 中文说明)
_RECRUIT_RESULTS = {
    "first_pass": (Application.Status.FIRST_PASS, roles.LEVEL_PREPARATORY, "一面通过 · 晋升预备会员"),
    "second_pass": (Application.Status.SECOND_PASS, roles.LEVEL_FORMAL, "二面通过 · 晋升科协会员"),
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
    page = None
    status_tabs = []
    interest_rows = []
    channel_rows = []
    total_count = 0
    if campaign:
        base = campaign.applications.select_related("user", "user__position")
        counts = {row["status"]: row["c"] for row in base.values("status").annotate(c=Count("id"))}
        total_count = sum(counts.values())
        status_tabs = [(value, label, counts.get(value, 0)) for value, label in Application.Status.choices]
        # 显式补 id 当次序的第二关键字。`Meta.ordering` 只有 `created_at`，两条
        # 同一微秒的记录在分页下的先后就没定义了 —— 那会让同一条记录在两页里
        # 重复出现或者干脆消失，而页面照常渲染。
        applications = (base if status not in Application.Status.values
                        else base.filter(status=status)).order_by("created_at", "id")

        if request.GET.get("export") == "csv":
            import csv
            from urllib.parse import quote

            from django.http import HttpResponse

            response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
            filename = quote(f"{campaign.name}-报名名单.csv")
            response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
            writer = csv.writer(response)
            writer.writerow([header for header, _ in _APPLICATION_CSV_COLUMNS])
            for a in applications:
                writer.writerow([get(a) for _, get in _APPLICATION_CSV_COLUMNS])
            return response

        # 两组多选的分布。**按当前筛选算**（页面上的标题也这么写）—— 筛到
        # 「二面通过」时看录取的这批人对什么感兴趣，比看全批次有用。
        #
        # 这里会把整个筛选结果取回内存（`_breakdown` 要遍历）。几百条的量级没问题，
        # 而换成按项发 `contains` 查询是 9 + 6 = 15 次往返，反而更贵。
        rows = list(applications)
        interest_rows = Application.interest_breakdown(rows)
        channel_rows = Application.channel_breakdown(rows)

        # **分页必须排在导出之后。** 反过来的话导出的 CSV 只有当前那一页 ——
        # 站务拿到一份 25 行的名单当成全部，而文件能正常打开、没有任何提示。
        page = Paginator(rows, 25).get_page(request.GET.get("page"))
        applications = page

    context = {
        "active_nav": "recruitment",
        "campaigns": campaigns,
        "campaign": campaign,
        "applications": applications,
        "page": page,
        "status": status,
        "status_tabs": status_tabs,
        "interest_rows": interest_rows,
        "channel_rows": channel_rows,
        "total_count": total_count,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "dashboard/recruitment.html", context)


@officer_required
def application_detail(request, pk: int):
    """单条报名的完整答卷。

    **为什么要有这一页**：纸质申请表的字段并进来之后，一条报名有十几项内容
    （两组多选 + 三个开放题 + 档案），列表页那张表塞不进去。原来自我介绍全文
    只能靠 `title` 属性的 tooltip 看 —— 那在触屏上压根打不开。

    改状态复用 `_apply_recruit_result`，和列表页的批量操作是同一份实现 ——
    不写第二份，否则「单条改」和「批量改」的副作用迟早漂开（一边发通知一边不发）。
    """
    application = get_object_or_404(
        Application.objects.select_related("user", "user__position", "campaign"), pk=pk,
    )

    if request.method == "POST":
        key = request.POST.get("result", "")
        if key not in _RECRUIT_RESULTS:
            messages.error(request, "未知操作。")
        else:
            _apply_recruit_result(
                application, key, (request.POST.get("note") or "").strip(), request.user,
            )
            messages.success(request, f"已更新：{_RECRUIT_RESULTS[key][2]}。")
        return redirect("dashboard:application_detail", pk=pk)

    context = {
        "active_nav": "recruitment",
        "application": application,
        # (键, 中文说明)，顺序跟着动作表 —— 模板不该自己再抄一遍这四个键
        "results": [(key, spec[2]) for key, spec in _RECRUIT_RESULTS.items()],
    }
    return render(request, "dashboard/application_detail.html", context)


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

    # 同上：annotate() 的 GROUP BY 让 Meta.ordering 失效，而这个列表要分页
    items = Project.objects.select_related("created_by").annotate(
        member_total=Count("members", distinct=True),
        file_total=Count("files", distinct=True),
    ).order_by("status", "-updated_at")
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
        # 必须接 request.FILES：表单里有展示封面。漏了它不会报错，只是封面
        # 永远存不上 —— 保存成功、页面正常、图没了。
        form = ProjectForm(request.POST, request.FILES, instance=project)
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


# ---------------------------------------------------------------- 素材中心（站务可用）

@officer_required
def media_slots(request):
    """素材中心：把「网站还缺哪些图」变成一份可以照着拍的清单。

    列表从 core/slots.py 的登记表出发，而不是从 MediaSlot 表出发 —— 这是整个
    设计的关键。还没人上传的槽位在数据库里没有行，若按表列就永远看不见它，
    而「缺什么」恰恰是站务最需要知道的信息。

    页面只列槽位、不列图片文件：站务的心智模型应该是「首页那一格该放什么」，
    不是「media 目录里有哪些文件」。
    """
    if request.method == "POST":
        return _media_slot_post(request)

    existing = {obj.key: obj for obj in MediaSlot.objects.select_related("updated_by")}

    groups = []
    for group, specs in slot_registry.by_group().items():
        cards = []
        for spec in specs:
            obj = existing.get(spec.key)
            cards.append({
                "spec": spec,
                "obj": obj,
                # 有兜底静态图的槽位不算「缺」：页面上那里有协会自己的照片，
                # 只是还没被更好的替换掉。清单要区分「空着」和「可以换更好的」。
                "state": ("filled" if obj and obj.is_active
                          else "off" if obj
                          else "fallback" if spec.fallback
                          else "missing"),
                "form": MediaSlotForm(instance=obj, prefix=_prefix(spec.key),
                                      kind=spec.kind),
            })
        groups.append({"name": group, "cards": cards})

    all_cards = [c for g in groups for c in g["cards"]]
    todo = sorted(
        [c for c in all_cards if c["state"] in ("missing", "fallback")],
        key=lambda c: (c["state"] != "missing", c["spec"].priority),
    )

    context = {
        "active_nav": "media",
        "groups": groups,
        "todo": todo,
        "total": len(all_cards),
        "filled": sum(1 for c in all_cards if c["state"] == "filled"),
        "missing": sum(1 for c in all_cards if c["state"] == "missing"),
        # 旧轮播图还留在库里，给一条搬进槽位的路径，别让站务手工下载再上传
        "legacy": CarouselImage.objects.all(),
        "slot_choices": [(s.key, f"{s.group} · {s.label}") for s in slot_registry.SLOTS],
        "focus_key": request.GET.get("key", ""),
    }
    return render(request, "dashboard/media_slots.html", context)


def _prefix(key: str) -> str:
    """表单前缀：一页上有十几个表单，字段名必须互不冲突。

    点号在 HTML name 里合法，但 Django 的表单前缀会拼成 `prefix-field`，
    保持简单起见换成下划线。
    """
    return key.replace(".", "_")


def _media_slot_post(request):
    """素材中心的三个写操作：上传/替换、启停、删除，外加旧轮播图搬迁。"""
    action = request.POST.get("action")
    key = request.POST.get("key", "")
    back = redirect(f"{reverse('dashboard:media_slots')}?key={key}" if key
                    else "dashboard:media_slots")

    if action == "migrate":
        return _migrate_carousel(request, back)

    spec = slot_registry.get(key)
    if spec is None:
        messages.error(request, f"没有登记过的素材槽「{key}」，请检查 core/slots.py。")
        return redirect("dashboard:media_slots")

    obj = MediaSlot.objects.filter(key=key).first()

    if action == "toggle":
        if not obj:
            messages.error(request, f"「{spec.label}」还没有上传过图。")
            return back
        obj.is_active = not obj.is_active
        obj.updated_by = request.user
        obj.save()
        messages.success(request, f"「{spec.label}」已{'启用' if obj.is_active else '停用'}。")
        return back

    if action == "delete":
        if obj:
            obj.image.delete(save=False)
            obj.delete()
            messages.success(request, f"「{spec.label}」的图已删除，该位置回到占位状态。")
        return back

    if action == "save":
        form = MediaSlotForm(request.POST, request.FILES, instance=obj,
                             prefix=_prefix(key), kind=spec.kind)
        if form.is_valid():
            oversized = form.oversized_videos()
            item = form.save(commit=False)
            item.key = key
            item.updated_by = request.user
            item.save()
            messages.success(request, f"「{spec.label}」已保存。")
            if oversized:
                # 不拦，只提醒：判断「这段画面值不值这么多流量」是人的事，
                # 但得让他知道自己传了多大。
                messages.warning(
                    request,
                    "以下文件超过建议体积（1.5MB）：" + "、".join(oversized)
                    + "。服务器没有 CDN，能压就压一下。",
                )
            return back
        # 表单有错就重新渲染整页，但只有出错那张卡片带着错误信息
        messages.error(request, f"「{spec.label}」保存失败：{_first_error(form)}")
        return back

    messages.error(request, "未知操作。")
    return redirect("dashboard:media_slots")


def _first_error(form) -> str:
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else field
        return f"{label} — {errors[0]}"
    return "请检查填写内容"


def _migrate_carousel(request, back):
    """把旧轮播图的图片文件复制进指定槽位。

    复制而不是移动：原记录留着，万一搬错了还能重来。搬完之后站务自己删旧记录。
    """
    from django.core.files.base import ContentFile

    item = CarouselImage.objects.filter(pk=request.POST.get("carousel_id")).first()
    key = request.POST.get("key", "")
    spec = slot_registry.get(key)
    if not item or spec is None:
        messages.error(request, "搬迁失败：轮播图或目标槽位不存在。")
        return redirect("dashboard:media_slots")

    obj, _ = MediaSlot.objects.get_or_create(key=key, defaults={"alt": item.title})
    with item.image.open("rb") as fh:
        obj.image.save(Path(item.image.name).name, ContentFile(fh.read()), save=False)
    obj.alt = obj.alt or item.title
    obj.caption = obj.caption or item.caption
    obj.is_active = True
    obj.updated_by = request.user
    obj.save()
    messages.success(
        request,
        f"已把「{item.title}」搬进「{spec.label}」。确认首页显示正常后可以删掉旧轮播图记录。",
    )
    return back


# ============================================================
#  荣誉墙录入
#  ------------------------------------------------------------
#  为什么必须有这一页而不能让站务用 Django Admin：站务是等级 4，而
#  `roles.sync_user_groups` 只在等级 5 才给 `is_staff` —— 站务打不开 Django Admin。
#  录奖这件事恰好就是站务在做。
# ============================================================


@officer_required
def honors_manage(request):
    from news.forms import HonorForm
    from news.models import Honor

    editing = None
    edit_pk = request.GET.get("edit")
    if edit_pk and edit_pk.isdigit():
        editing = get_object_or_404(Honor, pk=int(edit_pk))

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "delete":
            honor = get_object_or_404(Honor, pk=request.POST.get("id"))
            title = str(honor)
            if honor.certificate:
                honor.certificate.delete(save=False)
            honor.delete()
            messages.success(request, f"已删除「{title}」。")
            return redirect("dashboard:honors")

        if action == "toggle_public":
            honor = get_object_or_404(Honor, pk=request.POST.get("id"))
            honor.is_public = not honor.is_public
            # 撤回公开时连带撤掉首页展示，否则首页会指向一条已经不公开的记录
            if not honor.is_public:
                honor.is_featured = False
            honor.save(update_fields=["is_public", "is_featured"])
            messages.success(request, f"「{honor.title}」已{'公开' if honor.is_public else '撤回'}。")
            return redirect("dashboard:honors")

        if action == "toggle_featured":
            honor = get_object_or_404(Honor, pk=request.POST.get("id"))
            if not honor.is_public:
                messages.error(request, "要先公开这条记录，才能放到首页。")
            else:
                honor.is_featured = not honor.is_featured
                honor.save(update_fields=["is_featured"])
                messages.success(request, f"「{honor.title}」已{'加入' if honor.is_featured else '移出'}首页。")
            return redirect("dashboard:honors")

        # 保存（新建或修改）。**必须接 request.FILES** —— 表单里有证书照片
        target = None
        pk = request.POST.get("id")
        if pk and pk.isdigit():
            target = get_object_or_404(Honor, pk=int(pk))
        form = HonorForm(request.POST, request.FILES, instance=target)
        if form.is_valid():
            item = form.save()
            messages.success(request, f"「{item.title}」已{'更新' if target else '录入'}。")
            return redirect("dashboard:honors")
        messages.error(request, "有字段没填对，请看下面的提示。")
        editing = target
    else:
        form = HonorForm(instance=editing)

    from news.models import Honor as H

    context = {
        "active_nav": "honors",
        "form": form,
        "editing": editing,
        "items": H.objects.select_related("post").all(),
        "summary": H.summary(),
    }
    return render(request, "dashboard/honors.html", context)
