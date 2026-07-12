from django.urls import path

from . import views

app_name = "files"

urlpatterns = [
    path("", views.resource_list, name="list"),
    path("upload/", views.resource_upload, name="upload"),
    path("<int:pk>/download/", views.resource_download, name="download"),
]
