from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password/change/done/", views.PasswordChangeDoneView.as_view(), name="password_change_done"),
]
