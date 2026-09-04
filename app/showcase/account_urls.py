from django.urls import path
from . import views

urlpatterns = [
    path("", views.editor, name="showcase"),
    path("action/", views.action, name="showcase_action"),
    path("state/", views.state, name="showcase_state"),
    path("upload/", views.upload, name="showcase_upload"),
    path("assets/<uuid:asset_id>/delete/", views.remove_asset, name="showcase_asset_delete"),
]
