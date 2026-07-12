from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import LoginForm, ProfileForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
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


@login_required
def profile(request):
    my_resources = request.user.resources.all()[:20] if hasattr(request.user, "resources") else []
    return render(request, "accounts/profile.html", {"my_resources": my_resources})


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
