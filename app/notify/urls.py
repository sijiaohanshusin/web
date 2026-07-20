from django.urls import path

from . import views

app_name = "notify"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("latest.json", views.latest_json, name="latest_json"),
    path("<int:pk>/go/", views.notification_go, name="go"),
    path("read-all/", views.mark_all_read, name="read_all"),
]
