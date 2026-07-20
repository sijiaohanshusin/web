from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/folder/<int:folder_pk>/", views.project_detail, name="folder"),
    path("<int:pk>/folder/create/", views.create_folder, name="create_folder"),
    path("<int:pk>/upload/", views.upload_file, name="upload"),
    path("<int:pk>/file/<int:file_pk>/download/", views.project_file_download, name="download"),
    path("<int:pk>/file/<int:file_pk>/delete/", views.delete_file, name="delete_file"),
    path("<int:pk>/folder/<int:folder_pk>/delete/", views.delete_folder, name="delete_folder"),
    path("<int:pk>/members/", views.manage_members, name="members"),
]
