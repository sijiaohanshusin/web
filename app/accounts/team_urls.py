"""
公开团队页的路由，挂在 `/team/`（命名空间 `team:`）。

**刻意和 `accounts/urls.py` 分开**，理由和 Task 15 的 `projects/public_urls.py`
一样：那个 URLConf 里全是账号自助页面（注册/登录/找回密码/个人中心），一律
`@never_cache` + `no-store`、且大半要登录。团队页是给还没加入的人看的公开页面，
挂进去迟早被当成「账号页」一起加上禁缓存或登录门槛。
"""
from django.urls import path

from showcase import views

app_name = "team"

urlpatterns = [
    path("", views.wall, name="wall"),
    path("<uuid:public_id>/", views.detail, name="detail"),
]
