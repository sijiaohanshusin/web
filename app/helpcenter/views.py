import re
from pathlib import Path

import markdown
import nh3
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from . import content


def response(request, template, context, internal=False):
    result = render(request, template, context)
    result["Cache-Control"] = "private, no-store"
    patch_vary_headers(result, ["Cookie"])
    if internal:
        result["X-Robots-Tag"] = "noindex, nofollow"
    return result


def guide_data(user):
    return [{"key": key, **value, "count": len(content.visible(user, key))}
            for key, value in content.AUDIENCES.items()
            if key != "admin" or content.allowed(user, "officer") or content.allowed(user, "admin")]


@require_GET
def index(request):
    return response(request, "helpcenter/index.html", {"guides": guide_data(request.user)})


@require_GET
def guide(request, audience):
    if audience not in content.AUDIENCES:
        raise Http404
    articles = content.visible(request.user, audience)
    if audience == "admin" and not articles:
        raise Http404
    return response(request, "helpcenter/guide.html", {
        "guide": content.AUDIENCES[audience], "audience": audience, "articles": articles,
    }, audience == "admin")


def rendered(article):
    body = re.sub(r"\(asset:([a-zA-Z0-9_.-]+)\)", lambda m: f"({article.url}images/{m[1]}/)", article.body)
    renderer = markdown.Markdown(extensions=["extra", "toc", "sane_lists"],
                                 extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}})
    html = renderer.convert(body)
    attrs = {key: set(value) for key, value in nh3.ALLOWED_ATTRIBUTES.items()}
    for tag in ("h2", "h3"):
        attrs[tag] = {"id"}
    clean = nh3.clean(html, attributes=attrs)
    clean = clean.replace("<img ", '<img loading="lazy" decoding="async" ')
    return mark_safe(clean), mark_safe(nh3.clean(renderer.toc))


@require_GET
def article(request, audience, slug):
    item = content.find(request.user, audience, slug)
    if item is None:
        raise Http404
    items = content.visible(request.user, audience)
    position = items.index(item)
    html, toc = rendered(item)
    related = [a for a in content.visible(request.user) if a != item and set(a.routes) & set(item.routes)][:3]
    return response(request, "helpcenter/article.html", {
        "article": item, "guide": content.AUDIENCES[audience], "audience": audience,
        "html": html, "toc": toc, "articles": items, "related": related,
        "previous": items[position - 1] if position else None,
        "next": items[position + 1] if position + 1 < len(items) else None,
    }, audience == "admin")


@require_GET
def search(request):
    query = request.GET.get("q", "").strip()[:120]
    results = content.search(request.user, query)
    return response(request, "helpcenter/search.html", {"query": query, "results": results}, internal=True)


@never_cache
@require_GET
def image(request, audience, slug, name):
    item = content.find(request.user, audience, slug)
    if item is None or name not in item.screenshots or Path(name).name != name:
        raise Http404
    path = content.ROOT / "assets" / name
    if not path.is_file():
        raise Http404
    result = FileResponse(path.open("rb"), content_type="image/png")
    result["X-Content-Type-Options"] = "nosniff"
    result["X-Robots-Tag"] = "noindex"
    patch_vary_headers(result, ["Cookie"])
    return result
