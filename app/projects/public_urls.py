"""作品墙的公开路由，挂在 /works/。

和 `projects/urls.py`（会员档案库，挂在 /projects/）**分成两个 URLConf** 是有意的：
同一个 app 里两批完全不同受众的页面，路由分开写才不会出现「给外人的页面不小心
挂到了 /projects/ 下、被会员门槛拦住」或者反过来。命名空间也因此是两个：
`works:` 与 `projects:`。
"""
from django.urls import path

from . import views

app_name = "works"

urlpatterns = [
    path("", views.works_wall, name="wall"),
    path("<int:pk>/", views.works_detail, name="detail"),
]
