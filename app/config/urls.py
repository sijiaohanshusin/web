from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from showcase.views import deny_direct_asset

urlpatterns = [
    path("media/showcase/<path:path>", deny_direct_asset),
    path("showcase/", include("showcase.urls")),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("resources/", include("files.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("notify/", include("notify.urls")),
    path("news/", include("news.urls")),
    path("events/", include("events.urls")),
    path("points/", include("points.urls")),
    path("recruitment/", include("recruitment.urls")),
    # 同一个 projects app 挂两处：/projects/ 是会员档案库，/works/ 是公开作品墙。
    # 受众不同、门槛不同，路由分开写（见 projects/public_urls.py 的说明）。
    path("projects/", include("projects.urls")),
    path("works/", include("projects.public_urls")),
    # 荣誉墙。数据在 news app 里（Honor），但它是独立顶层页面、不是一篇公告，
    # 所以不挂在 /news/ 下面。
    path("honors/", include("news.honor_urls")),
    # 公开团队页。数据是 accounts.User + Position，但 /accounts/ 那个 URLConf 里
    # 全是要登录、要禁缓存的账号自助页，混进去迟早被一起加上门槛。
    path("team/", include("accounts.team_urls")),
    path("admin/", admin.site.urls),
]

admin.site.site_header = "HEU ESTA 管理后台"
admin.site.site_title = "HEU ESTA"
admin.site.index_title = "站点管理"

if settings.DEBUG:
    from showcase.demo import samples, photo, sample_detail
    from django.views.static import serve

    # 开发环境下模拟 nginx：直接服务 learn/ 学习中心与 media/
    urlpatterns += [
        path("team/design-demo/", samples),
        path("team/design-demo/photos/<slug:name>/", photo),
        path("team/design-demo/member-<int:index>/", sample_detail),
        path(
            "learn/<path:path>",
            serve,
            {"document_root": settings.REPO_DIR / "learn", "show_indexes": False},
        ),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
