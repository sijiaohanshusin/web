from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from core.models import SiteConfig

from . import roles, verification
from .forms import (
    CodeLoginForm,
    ForgotPasswordForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
)

User = get_user_model()

VALID_PURPOSES = {"register", "reset", "login"}


@require_POST
def send_code(request):
    """AJAX：发送邮箱验证码。用途 register/reset/login。"""
    email = (request.POST.get("email") or "").strip().lower()
    purpose = request.POST.get("purpose", "")
    if purpose not in VALID_PURPOSES:
        return JsonResponse({"ok": False, "msg": "非法的验证码用途。"}, status=400)
    if not email or "@" not in email:
        return JsonResponse({"ok": False, "msg": "请输入有效邮箱。"}, status=400)

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


def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    config = SiteConfig.load()
    if request.method == "POST":
        form = RegisterForm(request.POST)
        # 先校验验证码（表单其余字段有效时才验，避免浪费）
        if form.is_valid():
            email = form.cleaned_data["email"]
            try:
                verification.verify(email, "register", request.POST.get("code", ""))
            except verification.CodeError as e:
                form.add_error("code", str(e))
        if form.is_valid():
            user = form.save(commit=False)
            # 自动审核 / 内测模式决定初始等级
            if config.beta_mode:
                user.member_level = roles.LEVEL_OFFICER  # 内测：直接干事，测试全功能
                user.is_active = True
            elif config.auto_approve:
                user.member_level = roles.LEVEL_APPLICANT
                user.is_active = True
            else:
                user.member_level = roles.LEVEL_PENDING
                user.is_active = False
            user.save()
            roles.sync_user_groups(user)

            if user.is_active:
                login(request, user)
                messages.success(request, f"注册成功，欢迎加入！当前身份：{user.level_label}。")
                return redirect("core:home")
            return render(request, "accounts/register_done.html")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


def code_login(request):
    """验证码登录。"""
    if request.user.is_authenticated:
        return redirect("core:home")
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
                    return redirect("core:home")
    else:
        form = CodeLoginForm()
    return render(request, "accounts/code_login.html", {"form": form})


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
    return render(request, "accounts/profile.html", {
        "my_resources": my_resources,
        "my_medals": my_medals,
        "my_events": my_events,
        "my_points": total_for(request.user),
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
    return render(request, "accounts/profile_edit.html", {"form": form})


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        messages.success(self.request, "密码已修改。")
        return super().form_valid(form)


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"
