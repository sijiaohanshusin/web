from django.urls import path

from . import views

app_name = "points"

urlpatterns = [
    path("", views.mine, name="mine"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]
