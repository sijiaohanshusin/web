from django.urls import path

from . import views

app_name = "recruitment"

urlpatterns = [
    path("", views.index, name="index"),
    path("apply/", views.apply, name="apply"),
]
