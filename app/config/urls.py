from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("resources/", include("files.urls")),
    path("admin/", admin.site.urls),
]

admin.site.site_header = "HEU ESTA 管理后台"
admin.site.site_title = "HEU ESTA"
admin.site.index_title = "站点管理"

if settings.DEBUG:
    from django.views.static import serve

    # 开发环境下模拟 nginx：直接服务 learn/ 学习中心与 media/
    urlpatterns += [
        path(
            "learn/<path:path>",
            serve,
            {"document_root": settings.REPO_DIR / "learn", "show_indexes": False},
        ),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
