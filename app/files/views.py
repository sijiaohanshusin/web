from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.roles import effective_level, is_officer

from .forms import ResourceUploadForm
from .models import Resource


def resource_list(request):
    resources = Resource.objects.select_related("uploader")

    # 按用户有效等级过滤：只显示门槛不高于自己等级的资料
    level = effective_level(request.user)
    resources = resources.filter(min_level__lte=level)

    query = request.GET.get("q", "").strip()
    if query:
        resources = resources.filter(Q(title__icontains=query) | Q(description__icontains=query))

    category = request.GET.get("category", "")
    if category in Resource.Category.values:
        resources = resources.filter(category=category)

    paginator = Paginator(resources, 20)
    page = paginator.get_page(request.GET.get("page"))

    # 页头统计：当前用户可见范围内的总数 / 最近 7 天新增（不受搜索与分类筛选影响）
    visible = Resource.objects.filter(min_level__lte=level)
    week_ago = timezone.now() - timedelta(days=7)

    context = {
        "page": page,
        "query": query,
        "category": category,
        "categories": Resource.Category.choices,
        "can_upload": is_officer(request.user),
        "total_count": visible.count(),
        "week_count": visible.filter(created_at__gte=week_ago).count(),
    }
    return render(request, "files/list.html", context)


@login_required
@user_passes_test(is_officer)
def resource_upload(request):
    if request.method == "POST":
        form = ResourceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.uploader = request.user
            resource.save()
            messages.success(request, f"资料「{resource.title}」上传成功。")
            return redirect("files:list")
    else:
        form = ResourceUploadForm()
    return render(request, "files/upload.html", {"form": form})


def resource_download(request, pk: int):
    resource = get_object_or_404(Resource, pk=pk)

    if resource.min_level > 0:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if effective_level(request.user) < resource.min_level:
            return HttpResponseForbidden(
                f"该资料需要「{resource.get_min_level_display()}」才能下载。"
            )

    Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)

    if settings.DEBUG:
        return FileResponse(resource.file.open("rb"), as_attachment=True, filename=resource.filename)

    # 生产环境：Django 只做鉴权，文件传输交给 nginx（X-Accel-Redirect），不占应用内存
    response = HttpResponse()
    response["Content-Type"] = "application/octet-stream"
    response["X-Accel-Redirect"] = f"/protected/{quote(resource.file.name)}"
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(resource.filename)}"
    return response
