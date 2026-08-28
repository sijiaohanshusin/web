from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.roles import content_level, is_officer

from .models import Honor, Post


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

    # 未发布或尚未到发布时间的公告，仅站务管理可预览。
    live = post.is_published and post.published_at <= timezone.now()
    if not live and not is_officer(request.user):
        return HttpResponseForbidden("该公告尚未发布。")

    if post.min_level > 0:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if content_level(request.user) < post.min_level:
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


# ============================================================
#  荣誉墙（公开）
#  ------------------------------------------------------------
#  和上面的公告列表同一个 app，但是独立一页、独立 URLConf（news/honor_urls.py，
#  命名空间 honors，挂在 /honors/）。数据来自结构化的 Honor 而不是文章。
# ============================================================


def honor_wall(request):
    """荣誉墙：统计 + 证书条带 + 按年分组的完整清单。"""
    honors = list(Honor.wall())

    # 按年分组。用 Python 而不是数据库分组：这一页一次全取（几十条），而模板要的
    # 是「年份 → 该年列表」的嵌套结构，SQL 给不了。顺序已经由 Meta.ordering 定好，
    # 这里只是切段，不重新排序 —— 排序规则只有一处。
    by_year: list[tuple[int, list[Honor]]] = []
    for item in honors:
        if by_year and by_year[-1][0] == item.year:
            by_year[-1][1].append(item)
        else:
            by_year.append((item.year, [item]))

    context = {
        "summary": Honor.summary(),
        "by_year": by_year,
        # 证书条带只放真的有照片的。一张都没有时模板整段不渲染 ——
        # 二十个空占位框堆在页面顶部比没有这条带糟得多。
        "certificates": [h for h in honors if h.certificate][:8],
    }
    return render(request, "news/honors.html", context)
