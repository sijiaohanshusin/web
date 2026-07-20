from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("members/", views.members, name="members"),
    path("members/action/", views.member_action, name="member_action"),
    path("feedbacks/", views.feedbacks, name="feedbacks"),
    path("news/", views.news_manage, name="news"),
    path("news/new/", views.news_edit, name="news_create"),
    path("news/<int:pk>/edit/", views.news_edit, name="news_edit"),
    path("upload-image/", views.inline_image_upload, name="inline_image_upload"),
    path("events/", views.events_manage, name="events"),
    path("events/new/", views.event_edit, name="event_create"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("events/<int:pk>/signups/", views.event_signups, name="event_signups"),
    path("events/<int:pk>/qr.png", views.event_checkin_qr, name="event_qr"),
    path("recruitment/", views.recruitment_manage, name="recruitment"),
    path("recruitment/campaign/new/", views.campaign_edit, name="campaign_create"),
    path("recruitment/campaign/<int:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("medals/", views.medals, name="medals"),
    path("positions/", views.positions, name="positions"),
    path("resources/", views.resources, name="resources"),
    path("resources/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    path("site/", views.site_settings, name="site_settings"),
    path("site/carousel/<int:pk>/", views.carousel_update, name="carousel_update"),
]
