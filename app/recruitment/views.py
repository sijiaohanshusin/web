from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from accounts.roles import LEVEL_APPLICANT, LEVEL_FORMAL, effective_level

from .forms import ApplicationForm
from .models import Application, Campaign


def _current_campaign():
    """见 Campaign.current()。逻辑挪到模型上了，这里保留一层薄壳不动调用点。"""
    return Campaign.current()


def _campaign_stats(campaign) -> dict:
    """本批次的实时报名数据。

    「用真实数据当叙事」是这套设计语言的一条 —— 一个正在长的数字比一句
    「快来报名」有说服力得多。一次 group by 拿齐，不要按部门各查一次。
    """
    if campaign is None:
        return {"total": 0, "by_dept": {}}
    rows = (campaign.applications
            .values_list("department")
            .annotate(n=Count("id")))
    by_dept = {dept: n for dept, n in rows}
    return {
        "total": sum(by_dept.values()),
        "by_dept": by_dept,
        # 模板里要按固定顺序显示三条，顺手把标签也备好
        "breakdown": [
            (label, by_dept.get(value, 0))
            for value, label in Application.Department.choices
        ],
    }


@never_cache
def index(request):
    campaign = _current_campaign()
    my_app = None
    can_apply = False
    already_member = False

    if campaign and request.user.is_authenticated:
        my_app = Application.objects.filter(campaign=campaign, user=request.user).first()
        # 已是科协会员及以上，无需再报名
        already_member = effective_level(request.user) >= LEVEL_FORMAL
        can_apply = campaign.is_open and my_app is None and not already_member

    context = {
        "campaign": campaign,
        "my_app": my_app,
        "can_apply": can_apply,
        "already_member": already_member,
        "form": ApplicationForm(),
        "stats": _campaign_stats(campaign),
        # 报名进度时间线的节点定义放视图里，模板只管画。
        # 「未录取」不是第四个节点而是一个终止态，见模板注释。
        "progress_steps": Application.PROGRESS_STEPS,
    }
    return render(request, "recruitment/index.html", context)


@login_required
@never_cache
def apply(request):
    campaign = _current_campaign()
    if campaign is None or not campaign.is_open:
        messages.error(request, "当前没有正在进行的招新。")
        return redirect("recruitment:index")

    if effective_level(request.user) >= LEVEL_FORMAL:
        messages.info(request, "你已经是科协会员，无需报名招新。")
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

    # 兼容旧待审核账号；新会员注册时已经是招新成员。
    if effective_level(request.user) < LEVEL_APPLICANT:
        request.user.set_level(LEVEL_APPLICANT, note=f"招新报名：{campaign.name}")

    messages.success(request, "报名成功！请留意面试通知，结果会通过站内通知告诉你。")
    return redirect("recruitment:index")
