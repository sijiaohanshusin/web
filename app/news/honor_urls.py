"""荣誉墙的路由，挂在 /honors/。

和 `news/urls.py`（公告，挂在 /news/）分成两个 URLConf 的原因很简单：荣誉墙是
一个独立的顶层页面，不该落在 `/news/` 下面 —— 它不是一篇公告。命名空间 `honors:`。

和 `projects/public_urls.py`（作品墙）是同一个套路。
"""
from django.urls import path

from . import views

app_name = "honors"

urlpatterns = [
    path("", views.honor_wall, name="wall"),
]
