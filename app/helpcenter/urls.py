from django.urls import path
from . import views

app_name = "helpcenter"
urlpatterns = [
    path("", views.index, name="index"),
    path("search/", views.search, name="search"),
    path("<slug:audience>/", views.guide, name="guide"),
    path("<slug:audience>/<slug:slug>/", views.article, name="article"),
    path("<slug:audience>/<slug:slug>/images/<str:name>/", views.image, name="image"),
]
