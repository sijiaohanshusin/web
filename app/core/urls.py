from django.urls import path, re_path

from . import views, seo

app_name = "core"

urlpatterns = [
    path("sitemap.xml", seo.sitemap, name="sitemap"),
    path("health/ready/", views.readiness, name="readiness"),
    path("", views.home, name="home"),
    path("recruit/", views.recruit, name="recruit"),
    re_path(r"^learn(?:/.*)?$", views.learning_paused, name="learning_paused"),
    path("privacy/", views.privacy, name="privacy"),
    path("feedback/", views.feedback, name="feedback"),
    path("feedback/<int:pk>/", views.feedback_detail, name="feedback_detail"),
]
