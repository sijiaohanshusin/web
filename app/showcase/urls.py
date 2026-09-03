from django.urls import path
from . import views

app_name = "showcase"
urlpatterns = [
    path("assets/<uuid:asset_id>/<str:size>/", views.asset, name="asset"),
    path("moderation/", views.moderation, name="moderation"),
]
