from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("<int:pk>/", views.event_detail, name="detail"),
    path("<int:pk>/signup/", views.event_signup, name="signup"),
    path("<int:pk>/cancel/", views.event_cancel, name="cancel"),
    path("<int:pk>/checkin/", views.event_checkin, name="checkin"),
]
