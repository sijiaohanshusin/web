from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.roles import effective_level, is_officer
from notify.models import Notification
from notify.services import notify_user
from points.models import PointLog
from points.services import award_points

from .models import Event, EventSignup


def event_list(request):
    events = Event.objects.published().visible_to(request.user).select_related("created_by")

    kind = request.GET.get("kind", "")
    if kind in Event.Kind.values:
        events = events.filter(kind=kind)

    tab = request.GET.get("tab", "upcoming")
    now = timezone.now()
    if tab == "past":
        events = events.filter(end_at__lt=now).order_by("-start_at")
    else:
        tab = "upcoming"
        events = events.filter(end_at__gte=now).order_by("start_at")

    paginator = Paginator(events, 12)
    page = paginator.get_page(request.GET.get("page"))

    my_signup_ids = set()
    if request.user.is_authenticated:
        my_signup_ids = set(
            EventSignup.objects.filter(user=request.user, event__in=page.object_list)
            .values_list("event_id", flat=True)
        )

    context = {
        "page": page,
        "tab": tab,
        "kind": kind,
        "kinds": Event.Kind.choices,
        "my_signup_ids": my_signup_ids,
    }
    return render(request, "events/list.html", context)


def event_detail(request, pk: int):
    event = get_object_or_404(Event.objects.select_related("created_by"), pk=pk)

    officer = is_officer(request.user)
    if not event.is_published and not officer:
        return HttpResponseForbidden("该活动尚未发布。")
    if event.min_level > 0:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if effective_level(request.user) < event.min_level and not officer:
            return HttpResponseForbidden(f"该活动需要「{event.get_min_level_display()}」才能查看和报名。")

    my_signup = None
    if request.user.is_authenticated:
        my_signup = EventSignup.objects.filter(event=event, user=request.user).first()

    signup_count = event.signups.count()
    checkin_count = event.signups.filter(checkin_at__isnull=False).count()
    spots_left = max(event.capacity - signup_count, 0) if event.capacity else None

    can_signup = (
        request.user.is_authenticated
        and my_signup is None
        and not event.signup_closed
        and not event.is_finished
        and (event.capacity == 0 or signup_count < event.capacity)
    )

    context = {
        "event": event,
        "my_signup": my_signup,
        "signup_count": signup_count,
        "checkin_count": checkin_count,
        "spots_left": spots_left,
        "can_signup": can_signup,
        "can_manage": officer,
        # 扫码进来自动带上口令
        "prefill_code": (request.GET.get("code") or "").strip().upper()[:6],
    }
    return render(request, "events/detail.html", context)


@login_required
@require_POST
def event_signup(request, pk: int):
    event = get_object_or_404(Event, pk=pk, is_published=True)

    if effective_level(request.user) < event.min_level:
        messages.error(request, f"报名需要「{event.get_min_level_display()}」。")
        return redirect(event.get_absolute_url())
    if event.signup_closed or event.is_finished:
        messages.error(request, "报名已截止。")
        return redirect(event.get_absolute_url())

    try:
        with transaction.atomic():
            locked = Event.objects.select_for_update().get(pk=event.pk)
            count = locked.signups.count()
            if locked.capacity and count >= locked.capacity:
                messages.error(request, "名额已满，下次早点来！")
                return redirect(event.get_absolute_url())
            EventSignup.objects.create(event=locked, user=request.user)
    except IntegrityError:
        messages.info(request, "你已经报过名了。")
        return redirect(event.get_absolute_url())

    notify_user(
        request.user, f"报名成功：{event.title}",
        kind=Notification.Kind.EVENT,
        body=f"{event.start_at:%m 月 %d 日 %H:%M} · {event.location or '地点见详情'}",
        url=event.get_absolute_url(),
    )
    messages.success(request, "报名成功！开场前记得来签到。")
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def event_cancel(request, pk: int):
    event = get_object_or_404(Event, pk=pk)
    signup = EventSignup.objects.filter(event=event, user=request.user).first()
    if signup is None:
        messages.info(request, "你还没有报名该活动。")
    elif signup.checked_in:
        messages.error(request, "已签到的报名不能取消。")
    elif event.is_finished:
        messages.error(request, "活动已结束。")
    else:
        signup.delete()
        messages.success(request, "已取消报名。")
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def event_checkin(request, pk: int):
    event = get_object_or_404(Event, pk=pk, is_published=True)
    code = (request.POST.get("code") or "").strip().upper()

    if not event.checkin_open:
        messages.error(request, "签到未开放，请等待工作人员开启。")
        return redirect(event.get_absolute_url())
    if not code or code != event.checkin_code:
        messages.error(request, "签到口令不对，再核对一下现场公布的口令。")
        return redirect(event.get_absolute_url())
    if effective_level(request.user) < event.min_level:
        messages.error(request, f"参加该活动需要「{event.get_min_level_display()}」。")
        return redirect(event.get_absolute_url())

    signup, created = EventSignup.objects.get_or_create(
        event=event, user=request.user, defaults={"is_walkin": True},
    )
    if signup.checked_in:
        messages.info(request, "你已经签到过了。")
        return redirect(event.get_absolute_url())

    signup.checkin_at = timezone.now()
    signup.save(update_fields=["checkin_at"])

    if event.points_reward:
        award_points(
            request.user, event.points_reward,
            source=PointLog.Source.EVENT_CHECKIN, note=f"活动签到：{event.title}",
        )
        notify_user(
            request.user, f"签到成功，积分 +{event.points_reward}",
            kind=Notification.Kind.POINTS,
            body=f"{event.title}{'（现场参加）' if created else ''}",
            url="/points/",
        )
        messages.success(request, f"签到成功！积分 +{event.points_reward}。")
    else:
        messages.success(request, "签到成功！")
    return redirect(event.get_absolute_url())
