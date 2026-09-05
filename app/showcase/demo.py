"""Independent fictional fixtures. These routes and photos exist only in DEBUG."""
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

from .schema import DIRECTIONS, PAGE_MODULES, empty_design

PHOTO_NAMES = {"soldering", "maker", "signal", "builder"}


def fixtures():
    members = []
    for index, (name, year, direction, template, photo, intro, tags) in enumerate([
        ("林序", "2025", "hardware", "gallery", "soldering", "把想法，焊进现实。", ["嵌入式", "电路设计"]),
        ("陈知远", "2024", "hardware", "gallery", "maker", "从原理图，到第一声回应。", ["硬件开发"]),
        ("苏禾", "2024", "software", "type", "", "保持好奇，\n让想法发生。", ["开源", "交互设计"]),
        ("周屿", "2023", "software", "gallery", "signal", "让每一次尝试，都有回响。", ["嵌入式", "开源硬件"]),
        ("许知微", "2023", "custom", "gallery", "builder", "在技术与日常之间，\n找到新的可能。", []),
        ("顾行", "2022", "software", "plate", "", "记录、拆解，\n再重新创造。", ["Linux", "工具开发"]),
    ]):
        design = empty_design()
        design["card"].update(template=template, texture="none" if photo else "grid")
        design["card"]["background"].update(mode="photo" if photo else "gradient", preset="ivory" if index == 2 else "graphite")
        design["page"].update(template=template, modules=["intro", "skills", "works", "gallery", "links", "history"])
        if index == 3:
            design["card"]["modules"] = ["intro", "work", "tags"]
        url = f"/team/design-demo/photos/{photo}/" if photo else ""
        cover = url or ("/team/design-demo/photos/signal/" if template == "plate" else "")
        work_photo = "/team/design-demo/photos/signal/" if direction == "software" else "/team/design-demo/photos/soldering/"
        works = [{"id": f"demo-{index}-work", "title": "信号采集与可视化工具", "url": "", "image": work_photo,
                  "large_image": work_photo, "description": "从原理验证到可用界面，记录一次完整的设计迭代。"}]
        gallery = [{"image": "/team/design-demo/photos/builder/", "caption": "在实践里校准每一个细节。"},
                   {"image": "/team/design-demo/photos/maker/", "caption": "从一块电路板开始。"}]
        members.append({"url": f"/team/design-demo/member-{index}/", "nickname": name, "initial": name[0], "cohort": year,
            "direction": DIRECTIONS[direction], "direction_key": direction, "direction_detail": "设计与技术" if index == 4 else "",
            "position": {"name": "硬件副主席", "term": "2025–2026 届"} if index == 1 else None,
            "card": design["card"], "page": design["page"], "background": url, "background_small": url,
            "avatar": f"/team/design-demo/photos/{'maker' if index == 0 else photo}/" if index in {0, 1, 3} else "",
            "cover": cover, "intro": intro,
            "about": "热爱把抽象的想法拆解、设计、实现并打磨到可用。\n在实践中学习，也愿意把过程记录下来与伙伴分享。",
            "tags": tags, "skills": "开源协作 / 工程实践 / 工具开发\n正在学习：从需求分析到系统验证。",
            "works": works, "gallery": gallery, "links": [{"label": "协会网站", "url": "https://heuesta.cn/"}],
            "history": [{"name": "项目组成员", "term": "2024–2025 届", "current": False}], "medals": [],
            "page_modules": [{"kind": kind, "label": PAGE_MODULES[kind]} for kind in design["page"]["modules"]]})
    for member in members:
        member["featured_work"] = member["works"][0] if member["works"] else None
    return members


def samples(request):
    if not settings.DEBUG:
        raise Http404
    members = fixtures()
    filters = {key: request.GET.get(key, "").strip()[:80] for key in ("q", "cohort", "direction", "position")}
    filters["sort"] = "cohort_asc" if request.GET.get("sort") == "cohort_asc" else "cohort_desc"
    if request.GET.get("stress") == "1":
        members[0]["nickname"] = "这是三十字以内用来验证长昵称与官方身份区域的虚构测试成员"
        members[0]["intro"] = "很长的公开介绍用于确认裁切稳定，不应挤压昵称与身份，也不应产生卡片内部滚动条。" * 1
        members[0]["tags"] = ["十二字长度的技能标签测试甲", "十二字长度的技能标签测试乙", "开源", "工程"]
        members[0]["position"] = {"name": "硬件副主席", "term": "2025–2026 届"}
        members[0]["card"]["modules"] = ["intro", "tags", "work"]
        members[0]["works"] = [{"title": "用于长内容测试的精选作品", "url": "", "image": ""}]
        members[0]["featured_work"] = members[0]["works"][0]
        members[1]["background"] = members[1]["background_small"] = "/team/design-demo/photos/missing/"
    selected = [m for m in members if
        (not filters["q"] or filters["q"].lower() in (m["nickname"] + " ".join(m["tags"])).lower()) and
        (not filters["cohort"] or filters["cohort"] == m["cohort"]) and
        (not filters["direction"] or filters["direction"] == m["direction_key"]) and
        (not filters["position"] or (filters["position"] == "1" and m["position"]))]
    selected.sort(key=lambda m: m["cohort"], reverse=filters["sort"] == "cohort_desc")
    page = Paginator(selected, 24).get_page(request.GET.get("page"))
    context = {"members": page.object_list, "page": page, "demo": True, "filters": filters,
        "cohorts": ["2025", "2024", "2023", "2022"], "directions": DIRECTIONS,
        "positions": [SimpleNamespace(pk=1, name="硬件副主席")], "wall_url": "/team/design-demo/",
        "filtered": any(filters[k] for k in ("q", "cohort", "direction", "position")),
        "show_filters": True, "show_search": True, "show_cohort": True,
        "show_direction": True, "show_position": True, "show_sort": True}
    response = render(request, "showcase/results.html" if request.headers.get("X-Showcase-Partial") == "1" else "showcase/wall.html", context)
    patch_vary_headers(response, ["X-Showcase-Partial"])
    return response


def photo(request, name):
    if not settings.DEBUG or name not in PHOTO_NAMES:
        raise Http404
    return FileResponse((Path(__file__).parent / "demo_assets" / f"{name}.png").open("rb"), content_type="image/png")


def sample_detail(request, index):
    if not settings.DEBUG or not 0 <= index < 6:
        raise Http404
    return render(request, "showcase/detail.html", {"member": fixtures()[index], "demo": True})
