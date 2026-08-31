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


# 证书条带常显几张。
#
# 10 = 桌面上正好**两整行**：网格是 `auto-fill minmax(220px, 1fr)`，1240 容器下
# 每行 5 张。先试的 8 在桌面上是 5+3，第二行右边空一块，看着像图没加载出来。
#
# 每行几张随视口变（窄一点就是 4 张），所以没有哪个数在所有宽度下都是整行 ——
# 按桌面 1240 那一档取整，那是这一页的主视图。
CERT_STRIP_VISIBLE = 10


def honor_wall(request):
    """荣誉墙：统计 + 证书条带 + 按年分组的完整清单。"""
    honors = list(Honor.wall())
    certs = [h for h in honors if h.certificate]

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
        # 证书条带：**精选常显 + 其余折起来**，两段加起来是全部。
        #
        # 演进记录（两次都是真问题）：
        #   1. 原来写 `[:8]`，于是 13 张证书里有 5 张只存在数据库里 —— 年份清单
        #      那些行不显示证书（见 honor_row.html），条带是唯一的出口。
        #      存了却看不见等于没存，而这件事不会以任何形式报错。
        #   2. 于是改成全放。可扩到 35 张之后，条带在页面上占了七行约 2400px，
        #      把「全部记录」整段挤到了首屏之外 —— 而那一段才是这一页的主体。
        #
        # 所以拆两段：前 8 张常显（够证明「这是真的」），其余进一个默认收起的
        # `<details class="fold">`（core.css 的共用件）。**两段不重叠、加起来是全部**，
        # 那条「每张证书都要能在页面上看到」的断言照旧成立。
        # 顺序由 Meta.ordering 定（年份降序 + 等级），所以常显的自然是最近、
        # 最高等级的那几张。
        "certificates": certs[:CERT_STRIP_VISIBLE],
        "certificates_more": certs[CERT_STRIP_VISIBLE:],
    }
    return render(request, "news/honors.html", context)
