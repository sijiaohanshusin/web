from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("members/", views.members, name="members"),
    path("members/action/", views.member_action, name="member_action"),
    path("members/returning/<int:pk>/review/", views.returning_review, name="returning_review"),
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
    # 单条报名的完整答卷。**排在 campaign/ 之后**：`<int:pk>` 不会匹配到
    # "campaign" 这个词，所以其实不冲突，但按「具体路径在前、参数路径在后」排
    # 是这份文件的既有顺序。
    path("recruitment/<int:pk>/", views.application_detail, name="application_detail"),
    path("projects/", views.projects_manage, name="projects"),
    path("projects/new/", views.project_edit, name="project_create"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    # 荣誉录入。站务是等级 4、没有 is_staff，打不开 Django Admin，
    # 而录奖恰好就是站务在做的事 —— 所以必须有这一页。
    path("honors/", views.honors_manage, name="honors"),
    path("medals/", views.medals, name="medals"),
    path("positions/", views.positions, name="positions"),
    path("resources/", views.resources, name="resources"),
    path("resources/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    # 素材中心。名字别改：{% slot %} 的占位框靠 reverse('dashboard:media_slots')
    # 决定要不要显示上传入口，改名会让入口静默消失。
    path("media/", views.media_slots, name="media_slots"),
    path("site/", views.site_settings, name="site_settings"),
    path("site/carousel/<int:pk>/", views.carousel_update, name="carousel_update"),
]
