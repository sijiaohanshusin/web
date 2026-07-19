from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("members/", views.members, name="members"),
    path("members/action/", views.member_action, name="member_action"),
    path("medals/", views.medals, name="medals"),
    path("positions/", views.positions, name="positions"),
    path("resources/", views.resources, name="resources"),
    path("resources/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    path("site/", views.site_settings, name="site_settings"),
    path("site/carousel/<int:pk>/", views.carousel_update, name="carousel_update"),
]
