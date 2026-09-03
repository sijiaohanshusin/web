"""Only this explicit public DTO reaches member templates, never an account object."""
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.choices import position_term_label
from projects.models import Project

from .schema import DIRECTIONS, PAGE_MODULES


def asset_url(value, size="small"):
    return reverse("showcase:asset", args=[value, size]) if value else ""


def public_member(showcase, data):
    c = data["content"]
    account = showcase.user
    position = None
    if account.position_id:
        position = {"name": account.position.name, "term": account.position_term_label}
    public_projects = {str(p.pk): p for p in Project.public().filter(pk__in=[w["project"] for w in c["works"] if w["project"]])}
    works = []
    for work in c["works"]:
        project = public_projects.get(work["project"])
        # A project made private since publication must disappear from the DTO.
        if work["project"] and not project:
            continue
        works.append({"title": work["title"] or (project.name if project else "未命名作品"), "description": work["description"],
                      "image": asset_url(work["image"]), "url": project.public_url if project else work["url"]})
    history = []
    if "history" in data["page"]["modules"]:
        history = [{"name": a.position_name, "term": position_term_label(a.term_start), "current": a.ended_at is None}
                   for a in account.position_appointments.all()[:30]]
    medals = []
    if "medals" in data["page"]["modules"]:
        medals = [{"name": award.medal.name} for award in account.medals.select_related("medal").all()[:30]]
    return {
        "url": reverse("team:detail", args=[showcase.pk]),
        "nickname": data["nickname"] or "我的公开昵称", "initial": (data["nickname"] or "我")[0].upper(),
        "cohort": data["cohort"], "direction": data["direction_detail"] if data["direction"] == "custom" else DIRECTIONS[data["direction"]],
        "position": position, "card": data["card"], "page": data["page"],
        "avatar": asset_url(c["avatar"]), "cover": asset_url(c["cover"], "large"),
        "intro": c["intro"], "about": c["about"], "tags": c["tags"], "skills": c["skills"],
        "works": works, "gallery": [{"image": asset_url(g["image"], "large"), "caption": g["caption"]} for g in c["gallery"] if g["image"]],
        "links": c["links"], "history": history, "medals": medals,
        "legacy_medals": data.get("legacy_medals", []),
        "page_modules": [{"kind": m, "label": PAGE_MODULES[m]} for m in data["page"]["modules"]],
    }


def render_member(showcase, data, target="card"):
    member = public_member(showcase, data)
    return render_to_string(f"showcase/{target}.html", {"member": member, "preview": True})
