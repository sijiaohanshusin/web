from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from accounts.roles import LEVEL_APPLICANT, LEVEL_FORMAL, effective_level

from .forms import ApplicantProfileForm, ApplicationForm
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
        # 只有 can_apply 那一支会渲染它。匿名访客没有 User 实例可绑，
        # 也没必要为一个不会显示的表单造一个空 User。
        "profile_form": ApplicantProfileForm(instance=request.user) if can_apply else None,
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

    # 一次 POST 写两个模型：答卷进 Application，性别与出生日期进 User。
    # 两张 ModelForm 各管一个模型 —— 一张表写两个模型就得自己接管 save()，
    # 那是把 Django 的校验链拆开重焊。
    form = ApplicationForm(request.POST)
    profile_form = ApplicantProfileForm(request.POST, instance=request.user)

    # **两张都要跑 is_valid()，不能写 `a.is_valid() and b.is_valid()`** ——
    # `and` 会短路，第一张不合法时第二张压根不校验，于是它的错误一条都不显示，
    # 用户改完第一处提交又冒出新错误，来回好几趟。
    app_ok = form.is_valid()
    profile_ok = profile_form.is_valid()
    if not (app_ok and profile_ok):
        context = {
            "campaign": campaign, "my_app": None, "can_apply": True,
            "already_member": False, "form": form, "profile_form": profile_form,
            # 这两个原来漏了。模板里有 {% if %} 兜着所以不报错，但统计块会走空态
            # 分支 —— 校验失败一次，页面上的「N 人已报名」就凭空变没了。
            "stats": _campaign_stats(campaign),
            "progress_steps": Application.PROGRESS_STEPS,
        }
        return render(request, "recruitment/index.html", context)

    # 原子：要么两个模型都更新，要么一个都不动。分开存的话档案写成功而报名失败
    # （比如撞上唯一约束）会留下「资料改了但没报上名」，用户看不出发生了什么。
    with transaction.atomic():
        profile_form.save()
        application = form.save(commit=False)
        application.campaign = campaign
        application.user = request.user
        application.save()

        # 兼容旧待审核账号；新会员注册时已经是招新成员。
        if effective_level(request.user) < LEVEL_APPLICANT:
            request.user.set_level(LEVEL_APPLICANT, note=f"招新报名：{campaign.name}")

    messages.success(request, "报名成功！请留意面试通知，结果会通过站内通知告诉你。")
    return redirect("recruitment:index")
