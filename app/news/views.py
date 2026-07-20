from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.roles import effective_level, is_officer

from .models import Post


def post_list(request):
    posts = Post.objects.published().visible_to(request.user).select_related("author")

    category = request.GET.get("category", "")
    if category in Post.Category.values:
        posts = posts.filter(category=category)

    paginator = Paginator(posts, 12)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "category": category,
        "categories": Post.Category.choices,
    }
    return render(request, "news/list.html", context)


def post_detail(request, pk: int):
    post = get_object_or_404(Post.objects.select_related("author"), pk=pk)

    # 未发布/定时未到的只有干事及以上能预览
    live = post.is_published and post.published_at <= timezone.now()
    if not live and not is_officer(request.user):
        return HttpResponseForbidden("该公告尚未发布。")

    if post.min_level > 0:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if effective_level(request.user) < post.min_level:
            return HttpResponseForbidden(f"该公告需要「{post.get_min_level_display()}」才能查看。")

    Post.objects.filter(pk=pk).update(view_count=F("view_count") + 1)

    related = (
        Post.objects.published().visible_to(request.user)
        .filter(category=post.category).exclude(pk=post.pk)[:4]
    )
    context = {
        "post": post,
        "related": related,
        "can_manage": is_officer(request.user),
    }
    return render(request, "news/detail.html", context)
