import copy
import json
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Position
from projects.models import Project
from . import schema, services
from .models import Showcase, ShowcaseAsset, eligible
from .rendering import asset_url, public_member, render_member


def api_errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except services.Conflict as exc:
            return JsonResponse({"error": str(exc), "code": "conflict"}, status=409)
        except ValidationError as exc:
            return JsonResponse({"error": " ".join(exc.messages), "fields": getattr(exc, "message_dict", {"__all__": exc.messages})}, status=400)
        except PermissionDenied:
            return JsonResponse({"error": "当前账号或展示状态不允许此操作。"}, status=403)
    return wrapped


def body(request):
    if len(request.body) > 64 * 1024:
        raise ValidationError("设计内容过大。")
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("请求格式不正确。")
    if not isinstance(data, dict):
        raise ValidationError("请求格式不正确。")
    return data


@require_GET
def wall(request):
    queryset = Showcase.objects.visible().select_related("user__position")
    total_members = queryset.count()
    q = request.GET.get("q", "").strip()[:80]
    cohort = request.GET.get("cohort", "")
    direction = request.GET.get("direction", "")
    position = request.GET.get("position", "")
    sort = request.GET.get("sort", "cohort_desc")
    if sort not in {"cohort_desc", "cohort_asc"}:
        sort = "cohort_desc"
    cohorts = list(queryset.exclude(public_cohort="").order_by("-public_cohort").values_list("public_cohort", flat=True).distinct())
    direction_values = set(queryset.exclude(public_direction="").values_list("public_direction", flat=True).distinct())
    directions = {key: label for key, label in schema.DIRECTIONS.items() if key in direction_values}
    positions = list(Position.objects.filter(holders__showcase__in=queryset).distinct())
    if q:
        queryset = queryset.filter(Q(public_name__icontains=q) | Q(public_tags__icontains=q))
    if cohort:
        queryset = queryset.filter(public_cohort=cohort[:4])
    if direction:
        queryset = queryset.filter(public_direction=direction[:12])
    if position:
        queryset = queryset.filter(user__position_id=int(position)) if position.isdecimal() and len(position) < 10 else queryset.none()
    page = Paginator(queryset.order_by("public_cohort" if sort == "cohort_asc" else "-public_cohort", "public_name", "id"), 24).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    filtered = bool(q or cohort or direction or position)
    context = {"members": [public_member(sc, sc.published) for sc in page], "page": page,
        "filters": {"q": q, "cohort": cohort, "direction": direction, "position": position, "sort": sort}, "cohorts": cohorts,
        "directions": directions, "positions": positions, "querystring": query.urlencode(),
        "wall_url": reverse("team:wall"), "filtered": filtered, "total_members": total_members,
        "show_filters": bool(total_members or filtered), "show_search": bool(total_members >= 6 or q),
        "show_cohort": bool(len(cohorts) > 1 or cohort), "show_direction": bool(len(directions) > 1 or direction),
        "show_position": bool(len(positions) > 1 or position), "show_sort": total_members > 1}
    response = render(request, "showcase/results.html" if request.headers.get("X-Showcase-Partial") == "1" else "showcase/wall.html", context)
    patch_vary_headers(response, ["X-Showcase-Partial"])
    return response


@require_GET
def detail(request, public_id):
    sc = get_object_or_404(Showcase.objects.visible().select_related("user__position"), pk=public_id)
    if not schema.upgrade_design(sc.published)["publication"]["page"]:
        raise Http404
    return render(request, "showcase/detail.html", {"member": public_member(sc, sc.published)})


@login_required
@require_GET
def editor(request):
    if not eligible(request.user):
        return render(request, "showcase/ineligible.html", status=403)
    sc = services.get_showcase(request.user)
    options = {"templates": schema.TEMPLATES, "palettes": schema.PALETTES, "textures": schema.TEXTURES,
               "focus": schema.FOCUS, "shapes": schema.SHAPES, "cardModules": schema.CARD_MODULES, "pageModules": schema.PAGE_MODULES,
               "backgrounds": schema.BACKGROUNDS, "presets": schema.PRESETS, "blurs": schema.BLURS, "masks": schema.MASKS}
    data = state_data(sc)
    data.update(options=options, projects=[{"id": str(p.pk), "name": p.name, "url": p.public_url} for p in Project.public()])
    return render(request, "showcase/workspace.html", {
        "showcase": sc, "bootstrap": data,
        "cohorts": range(timezone.localdate().year, 1994, -1), "directions": schema.DIRECTIONS,
        "public_projects": Project.public(), "preview_card": render_member(sc, sc.draft),
        "public_url": reverse("team:detail", args=[sc.pk]), "official": public_member(sc, sc.draft)["position"],
    })


@login_required
@require_POST
@api_errors
def action(request):
    data = body(request)
    operation = data.get("action")
    if operation == "preview":
        if not eligible(request.user):
            raise PermissionDenied
        sc = services.get_showcase(request.user)
        if type(data.get("revision")) is not int or data["revision"] != sc.revision:
            raise services.Conflict("版本已变化，请保留当前内容并刷新后对照。")
        design = services.validate_owned(sc, data.get("design"))
        target = data.get("target", "card")
        if not isinstance(target, str) or target not in {"card", "page", "both", "templates"}:
            raise ValidationError("无效的预览类型。")
        if target == "templates":
            documents = {}
            for kind in ("card", "page"):
                for template in schema.TEMPLATES:
                    variant = copy.deepcopy(design)
                    variant[kind]["template"] = template
                    documents[kind + "-" + template] = render_to_string("showcase/preview.html", {"component": render_member(sc, variant, kind)})
            return JsonResponse({"documents": documents})
        if target == "both":
            return JsonResponse({"documents": {kind: render_to_string("showcase/preview.html", {"component": render_member(sc, design, kind)}) for kind in ("card", "page")},
                                 "ticket": services.preview_ticket(sc, design)})
        component = render_member(sc, design, target)
        return JsonResponse({"document": render_to_string("showcase/preview.html", {"component": component}), "ticket": services.preview_ticket(sc, design)})
    sc = services.change(request.user, operation, data.get("revision"), data.get("design"), data.get("consent"), data.get("ticket", ""))
    return JsonResponse({**state_data(sc), "message": {"save": "草稿已保存，公开内容未改变。", "publish": "已发布，成员墙现在展示这一版。", "withdraw": "已撤回，页面与图片已停止公开访问。"}[operation]})


def asset_uses(raw, *, public=False):
    if not raw:
        return {}
    data = schema.upgrade_design(raw)
    c, card, page = data["content"], data["card"], data["page"]
    publication = data["publication"]
    result = {}
    def add(aid, label):
        if aid:
            result.setdefault(aid, []).append(label)
    add(c["avatar"], "展示头像")
    if not public or card["background"]["mode"] == "photo":
        add(card["background"]["image"], "卡片背景")
    if not public or (publication["page"] and page["template"] in {"plate", "gallery"}):
        add(c["cover"], "个人页封面")
    projects = set(str(pk) for pk in Project.public().values_list("pk", flat=True)) if public else None
    for index, work in enumerate(c["works"]):
        if public and work["project"] and work["project"] not in projects:
            continue
        if not public or (publication["page"] and "works" in page["modules"]) or ("work" in card["modules"] and work["id"] == card["featured_work"]):
            add(work["image"], f"作品 {index + 1}")
    if not public or (publication["page"] and "gallery" in page["modules"]):
        for index, entry in enumerate(c["gallery"]):
            add(entry["image"], f"图集 {index + 1}")
    return result


def asset_list(sc):
    draft = asset_uses(sc.draft)
    public = asset_uses(sc.published, public=True) if sc.published and not sc.blocked else {}
    reserved = schema.referenced_assets(sc.published) if sc.published else set()
    result = []
    for index, a in enumerate(sc.assets.order_by("created_at")):
        aid = str(a.pk)
        try:
            size = a.byte_size or a.image.size
        except (OSError, ValueError):
            size = None
        result.append({"id": aid, "url": asset_url(a.pk), "large_url": asset_url(a.pk, "large"),
                       "width": a.width, "height": a.height, "name": a.display_name or f"素材 {index + 1}.jpg",
                       "format": "JPEG", "bytes": size, "draft_uses": draft.get(aid, []), "public_uses": public.get(aid, []),
                       "can_delete": aid not in draft and aid not in reserved,
                       "delete_url": reverse("accounts:showcase_asset_delete", args=[aid])})
    return result


def state_data(sc):
    published = schema.upgrade_design(sc.published) if sc.published else None
    return {"draft": schema.upgrade_design(sc.draft), "revision": sc.revision, "assets": asset_list(sc),
            "published": bool(published and not sc.blocked),
            "public_card": bool(published and published["publication"]["card"] and not sc.blocked),
            "public_page": bool(published and published["publication"]["page"] and not sc.blocked),
            "blocked": sc.blocked,
            "moderation_reason": sc.moderation_reason, "withdrawal_reason": sc.withdrawal_reason,
            "published_at": sc.published_at.isoformat() if sc.published_at else None,
            "saved_at": sc.updated_at.isoformat(), "public_url": reverse("team:detail", args=[sc.pk])}


@login_required
@require_GET
@api_errors
def state(request):
    if not eligible(request.user):
        raise PermissionDenied
    sc = Showcase.objects.filter(user=request.user).first()
    if not sc:
        return JsonResponse({"draft": schema.empty_design(), "revision": 0, "assets": [], "published": False,
                             "public_card": False, "public_page": False, "blocked": False})
    return JsonResponse(state_data(sc))


@login_required
@require_POST
@api_errors
def upload(request):
    if not eligible(request.user):
        raise PermissionDenied
    sc = services.get_showcase(request.user)
    if request.POST.get("copy_avatar") == "1":
        if not request.user.avatar:
            raise ValidationError("账号暂未设置头像。")
        try:
            with request.user.avatar.open("rb") as source:
                services.add_asset(request.user, source)
        except (OSError, ValueError):
            raise ValidationError("原头像无法读取，请重新上传。")
    else:
        file = request.FILES.get("image")
        if not file:
            raise ValidationError("请选择图片。")
        services.add_asset(request.user, file)
    return JsonResponse({"assets": asset_list(sc)})


@login_required
@require_POST
@api_errors
def remove_asset(request, asset_id):
    get_object_or_404(ShowcaseAsset, pk=asset_id, showcase__user=request.user)
    services.delete_asset(request.user, asset_id)
    return JsonResponse({"assets": asset_list(request.user.showcase)})


@require_GET
def asset(request, asset_id, size):
    a = get_object_or_404(ShowcaseAsset.objects.select_related("showcase__user"), pk=asset_id)
    sc = a.showcase
    owner = eligible(request.user) and request.user.pk == sc.user_id
    if not owner:
        if not Showcase.objects.visible().filter(pk=sc.pk).exists():
            raise Http404
        published = schema.upgrade_design(sc.published)
        projects = {str(pk) for pk in Project.public().values_list("pk", flat=True)}
        published["content"]["works"] = [w for w in published["content"]["works"] if not w["project"] or w["project"] in projects]
        if str(a.pk) not in schema.referenced_assets(published, visible_only=True):
            raise Http404
    if size not in {"small", "large"}:
        raise Http404
    file = a.thumbnail if size == "small" else a.image
    if settings.DEBUG:
        try:
            response = FileResponse(file.open("rb"), content_type="image/jpeg")
        except FileNotFoundError:
            raise Http404
    else:
        response = HttpResponse(content_type="image/jpeg")
        response["X-Accel-Redirect"] = "/protected/" + quote(file.name)
    response["Content-Disposition"] = 'inline; filename="member-image.jpg"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def deny_direct_asset(request, path=""):
    return HttpResponseForbidden("请从成员展示图片接口访问。")


@login_required
def moderation(request):
    if not request.user.is_officer:
        raise PermissionDenied
    if request.method == "POST":
        try:
            sc = get_object_or_404(Showcase, pk=request.POST.get("showcase"))
            services.moderate(request.user, sc.pk, request.POST.get("action"), request.POST.get("reason", ""))
            messages.success(request, "展示状态已更新；解除限制不会代替成员发布。")
            return redirect("showcase:moderation")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    elif request.method != "GET":
        return HttpResponse(status=405)
    # Administrators see status and the live public snapshot, never private drafts/assets.
    rows = [{"id": str(sc.pk), "label": sc.public_name or "未公开展示", "blocked": sc.blocked, "reason": sc.moderation_reason,
             "url": (reverse("team:detail", args=[sc.pk]) if sc.published and not sc.blocked
                     and schema.upgrade_design(sc.published)["publication"]["page"] else "")}
             for sc in Showcase.objects.filter(Q(published__isnull=False) | Q(blocked=True)).order_by("-updated_at")[:200]]
    return render(request, "showcase/moderation.html", {"rows": rows})
