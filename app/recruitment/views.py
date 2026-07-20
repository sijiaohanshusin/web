from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.roles import LEVEL_APPLICANT, LEVEL_FORMAL, effective_level

from .forms import ApplicationForm
from .models import Application, Campaign


def _current_campaign():
    """取最近一个启用的批次（优先进行中，否则最近的启用批次）用于展示。"""
    active = Campaign.objects.filter(is_active=True)
    for c in active.order_by("-opens_at"):
        if c.is_open:
            return c
    return active.order_by("-opens_at").first()


def index(request):
    campaign = _current_campaign()
    my_app = None
    can_apply = False
    already_member = False

    if campaign and request.user.is_authenticated:
        my_app = Application.objects.filter(campaign=campaign, user=request.user).first()
        # 已是正式会员及以上，无需再报名
        already_member = effective_level(request.user) >= LEVEL_FORMAL
        can_apply = campaign.is_open and my_app is None and not already_member

    context = {
        "campaign": campaign,
        "my_app": my_app,
        "can_apply": can_apply,
        "already_member": already_member,
        "form": ApplicationForm(),
    }
    return render(request, "recruitment/index.html", context)


@login_required
def apply(request):
    campaign = _current_campaign()
    if campaign is None or not campaign.is_open:
        messages.error(request, "当前没有正在进行的招新。")
        return redirect("recruitment:index")

    if effective_level(request.user) >= LEVEL_FORMAL:
        messages.info(request, "你已经是正式会员，无需报名招新。")
        return redirect("recruitment:index")

    if Application.objects.filter(campaign=campaign, user=request.user).exists():
        messages.info(request, "你已经报名了，不用重复提交。")
        return redirect("recruitment:index")

    if request.method != "POST":
        return redirect("recruitment:index")

    form = ApplicationForm(request.POST)
    if not form.is_valid():
        context = {
            "campaign": campaign, "my_app": None, "can_apply": True,
            "already_member": False, "form": form,
        }
        return render(request, "recruitment/index.html", context)

    application = form.save(commit=False)
    application.campaign = campaign
    application.user = request.user
    application.save()

    # 报名即挂到「报名会员」（若当前更低）
    if effective_level(request.user) < LEVEL_APPLICANT:
        request.user.set_level(LEVEL_APPLICANT, note=f"招新报名：{campaign.name}")

    messages.success(request, "报名成功！请留意面试通知，结果会通过站内通知告诉你。")
    return redirect("recruitment:index")
