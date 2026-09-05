from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.redirects import safe_return_url

from . import roles, verification
from .forms import (
    CodeLoginForm,
    ForgotPasswordForm,
    LoginForm,
    NewMemberRegisterForm,
    ProfileForm,
    ReturningMemberRegisterForm,
)
from .models import ReturningMembershipRequest

User = get_user_model()

VALID_PURPOSES = {"register", "reset", "login"}


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown"))


def _safe_next(request) -> str:
    """取 ?next= / POST next，只放行站内地址。

    整条注册链路都要带着它走：从招新页点「注册」的人，注册完应该回到招新页而
    不是首页。这个参数会经过「选通道 → 填表 → POST 回来重渲染」三跳，中间任何
    一跳丢了，用户就落到一个自己没要求去的地方。

    开放重定向是个真实漏洞（`?next=//evil.example`），所以一律过
    `url_has_allowed_host_and_scheme`，不合法就当没传。
    """
    target = request.POST.get("next") or request.GET.get("next") or ""
    return safe_return_url(request, target, "")


def _registration_rate_allowed(request) -> bool:
    """校园共享出口限流：单 IP 每小时最多 300 次有效注册尝试。"""
    key = f"register:hour:{_client_ip(request)}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3600)
        count = 1
    return count <= 300


@require_POST
def send_code(request):
    """AJAX：发送邮箱验证码。用途 register/reset/login。"""
    email = (request.POST.get("email") or "").strip().lower()
    purpose = request.POST.get("purpose", "")
    if purpose not in VALID_PURPOSES:
        return JsonResponse({"ok": False, "msg": "非法的验证码用途。"}, status=400)
    if not email or "@" not in email:
        return JsonResponse({"ok": False, "msg": "请输入有效邮箱。"}, status=400)

    ip_key = f"verify:ip:{_client_ip(request)}"
    try:
        ip_count = cache.incr(ip_key)
    except ValueError:
        cache.set(ip_key, 1, 3600)
        ip_count = 1
    if ip_count > 1000:
        return JsonResponse({"ok": False, "msg": "当前网络请求验证码过多，请稍后再试。"}, status=429)

    exists = User.objects.filter(email__iexact=email).exists()
    if purpose == "register" and exists:
        return JsonResponse({"ok": False, "msg": "该邮箱已注册。"}, status=400)
    if purpose in ("reset", "login") and not exists:
        return JsonResponse({"ok": False, "msg": "该邮箱未注册。"}, status=400)

    can, err = verification.can_send(email)
    if not can:
        return JsonResponse({"ok": False, "msg": err}, status=429)
    try:
        verification.issue(email, purpose)
    except Exception:
        return JsonResponse({"ok": False, "msg": "验证码发送失败，请稍后再试或联系管理员。"}, status=500)
    return JsonResponse({"ok": True, "msg": "验证码已发送，请查收邮箱（含垃圾箱）。"})


@never_cache
def register(request):
    """注册入口：明确区分新会员与老会员身份恢复。"""
    if request.user.is_authenticated:
        return redirect(_safe_next(request) or "core:home")
    return render(request, "accounts/register_choice.html", {
        "next": _safe_next(request),
    })


def _verify_registration_form(form, request) -> bool:
    if not form.is_valid():
        return False
    if not _registration_rate_allowed(request):
        form.add_error(None, "当前网络注册请求较多，请稍后再试。")
        return False
    try:
        verification.verify(form.cleaned_data["email"], "register", form.cleaned_data["code"])
    except verification.CodeError as exc:
        form.add_error("code", str(exc))
        return False
    return True


def _recruitment_is_open() -> bool:
    """当前有没有能报名的批次。决定新会员注册完该去哪。

    运行时导入：accounts 是最底层的 app，不在模块级依赖 recruitment。
    """
    from recruitment.models import Campaign

    campaign = Campaign.current()
    return bool(campaign and campaign.is_open)


@never_cache
def register_new(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request) or "core:home")

    form = NewMemberRegisterForm(request.POST or None)
    if request.method == "POST" and _verify_registration_form(form, request):
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.member_level = roles.LEVEL_APPLICANT
                user.is_active = True
                user.save()
                roles.sync_user_groups(user)
        except IntegrityError:
            form.add_error(None, "邮箱、学号或手机号已被注册，请核对后重试。")
        else:
            login(request, user)
            # 有报名可填就直接送过去（注册的动机通常就是它）；没有的话不要把人
            # 丢到一个写着「招新通道暂时关闭」的页面上 —— 那是个死胡同。改成
            # 完成页，明确说账号已经能用、现在能做什么。
            target = _safe_next(request)
            if target:
                messages.success(request, "注册成功！你已成为招新成员。")
                return redirect(target)
            if _recruitment_is_open():
                messages.success(request, "注册成功！你已成为招新成员，请继续完成招新报名。")
                return redirect("recruitment:index")
            return render(request, "accounts/register_done.html", {
                "channel": "new", "user_obj": user,
            })
    return render(request, "accounts/register_form.html", {
        "form": form, "channel": "new", "next": _safe_next(request),
    })


@never_cache
def register_returning(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request) or "core:home")

    form = ReturningMemberRegisterForm(request.POST or None)
    if request.method == "POST" and _verify_registration_form(form, request):
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.member_level = roles.LEVEL_PENDING
                user.is_active = False
                user.save()
                ReturningMembershipRequest.objects.create(
                    user=user,
                    requested_role=form.cleaned_data["requested_role"],
                )
        except IntegrityError:
            form.add_error(None, "邮箱、学号或手机号已被注册，请核对后重试。")
        else:
            # 老会员这条路不接 next：账号还没激活，去哪儿都是登录页
            return render(request, "accounts/register_done.html", {
                "channel": "returning", "returning": True, "user_obj": user,
            })
    return render(request, "accounts/register_form.html", {
        "form": form, "channel": "returning", "next": _safe_next(request),
    })


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_redirect_url(self):
        return safe_return_url(self.request, super().get_redirect_url(), "")


class LogoutView(auth_views.LogoutView):
    def get_redirect_url(self):
        return safe_return_url(self.request, super().get_redirect_url(), "")


@never_cache
def code_login(request):
    """验证码登录。

    `@never_cache`：表单里过的是一次性验证码，而 `DynamicPagesNoCacheMiddleware`
    只给 `private, no-cache`（可存、需回源校验）。登录态页面要的是 `no-store`。
    Django 自带的 LoginView 本身就带 never_cache，这一支是我们自己写的，得自己加。
    """
    if request.user.is_authenticated:
        return redirect(_safe_next(request) or "core:home")
    target = _safe_next(request)
    if request.method == "POST":
        form = CodeLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            try:
                verification.verify(email, "login", form.cleaned_data["code"])
            except verification.CodeError as e:
                form.add_error("code", str(e))
            else:
                if not user or not user.is_active:
                    form.add_error(None, "该账号不存在或待审核，暂时无法登录。")
                else:
                    login(request, user)
                    messages.success(request, "登录成功。")
                    return redirect(target or "core:home")
    else:
        form = CodeLoginForm()
    return render(request, "accounts/code_login.html", {"form": form, "next": target})


@never_cache
def forgot_password(request):
    """找回密码：邮箱 + 验证码 + 新密码。"""
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            try:
                verification.verify(email, "reset", form.cleaned_data["code"])
            except verification.CodeError as e:
                form.add_error("code", str(e))
            else:
                if not user:
                    form.add_error("email", "该邮箱未注册。")
                else:
                    user.set_password(form.cleaned_data["new_password1"])
                    user.save(update_fields=["password"])
                    messages.success(request, "密码已重置，请用新密码登录。")
                    return redirect("accounts:login")
    else:
        form = ForgotPasswordForm()
    return render(request, "accounts/forgot_password.html", {"form": form})


@login_required
def profile(request):
    from points.services import total_for

    my_resources = request.user.resources.all()[:20] if hasattr(request.user, "resources") else []
    my_medals = request.user.medals.select_related("medal").all()
    my_events = (
        request.user.event_signups.select_related("event").order_by("-created_at")[:10]
    )
    my_application = (
        request.user.applications.select_related("campaign").order_by("-created_at").first()
    )
    return render(request, "accounts/profile.html", {
        "my_resources": my_resources,
        "my_medals": my_medals,
        "my_events": my_events,
        "my_points": total_for(request.user),
        "my_application": my_application,
        "position_appointments": request.user.position_appointments.all()[:20],
        "showcase_summary": showcase_summary(request.user),
    })


@login_required
def profile_edit(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "资料已更新。")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_edit.html", {"form": form, "showcase_summary": showcase_summary(request.user)})


def showcase_summary(user):
    from showcase.models import Showcase
    from showcase.schema import upgrade_design

    sc = Showcase.objects.filter(user=user).first()
    if not sc:
        return {"label": "从第一张成员卡片开始", "reason": "无需担任职位，也不需要先做完整个人页。", "ready": 0}
    label = "被管理员下架" if sc.blocked else "已有公开版本" if sc.published and user.can_design_showcase else "已撤回" if sc.withdrawal_reason else "尚未公开"
    draft = upgrade_design(sc.draft)
    ready = sum(bool(value) for value in (draft["nickname"].strip(), draft["content"]["intro"].strip(), draft["content"]["tags"]))
    return {"label": label, "reason": sc.moderation_reason if sc.blocked else "", "saved_at": sc.updated_at, "ready": ready}


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        messages.success(self.request, "密码已修改。")
        return super().form_valid(form)


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


# Compatibility import for callers of the former team view.
def team_wall(request):
    from showcase.views import wall
    return wall(request)
