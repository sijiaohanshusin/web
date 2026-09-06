"""作品墙的公开路由，挂在 /works/。

和 `projects/urls.py`（会员档案库，挂在 /projects/）**分成两个 URLConf** 是有意的：
同一个 app 里两批完全不同受众的页面，路由分开写才不会出现「给外人的页面不小心
挂到了 /projects/ 下、被会员门槛拦住」或者反过来。命名空间也因此是两个：
`works:` 与 `projects:`。
"""
from django.urls import path

from . import views
from . import member_views

app_name = "works"

urlpatterns = [
    path("", views.works_wall, name="wall"),
    path("mine/", member_views.mine, name="mine"),
    path("new/", member_views.create, name="create"),
    path("manage/", member_views.ranking, name="ranking"),
    path("images/<uuid:image_pk>/", member_views.image, name="image"),
    path("mine/<uuid:pk>/", member_views.edit, name="edit"),
    path("mine/<uuid:pk>/preview/", member_views.preview, name="preview"),
    path("mine/<uuid:pk>/publish/", member_views.publish, name="publish"),
    path("mine/<uuid:pk>/withdraw/", member_views.withdraw, name="withdraw"),
    path("mine/<uuid:pk>/delete/", member_views.remove, name="delete"),
    path("mine/<uuid:pk>/images/<uuid:image_pk>/delete/", member_views.remove_image, name="delete_image"),
    path("<int:pk>/", views.works_detail, name="detail"),
]
