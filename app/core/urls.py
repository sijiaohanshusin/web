from django.urls import path, re_path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("recruit/", views.recruit, name="recruit"),
    re_path(r"^learn(?:/.*)?$", views.learning_paused, name="learning_paused"),
    path("privacy/", views.privacy, name="privacy"),
    path("feedback/", views.feedback, name="feedback"),
    path("feedback/<int:pk>/", views.feedback_detail, name="feedback_detail"),
]
