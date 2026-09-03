"""Fictional layout fixtures; mounted only in DEBUG, never a public member record."""
from django.shortcuts import render
from .schema import empty_design, PALETTES


def samples(request):
    palette = request.GET.get("palette", "cyan")
    if palette not in PALETTES:
        palette = "cyan"
    members = []
    for index, (template, name, intro) in enumerate([
        ("plate", "林序", "把一块电路板，从纸上的想法变成桌上的作品。"),
        ("gallery", "陈知远", "写一点代码，让复杂的问题变得清晰。"),
        ("type", "苏禾", "保持好奇。\n让每一次尝试都有回响。"),
        ("plate", "这是一个用于验证换行与截断效果的很长的公开昵称", "这是用于验证长介绍的虚构文字，排版不应挤压成员的昵称与官方身份信息。"),
        ("gallery", "无头像成员", "每一个认真做东西的人，都值得被看见。"),
        ("type", "周屿", "不急着定义方向，先把想做的东西做出来。"),
    ]):
        design = empty_design()
        design["card"].update(template=template, palette=palette)
        members.append({"nickname": name, "initial": name[0], "cohort": str(2025 - index % 3), "direction": "软件" if index % 2 else "硬件",
                        "position": {"name": "软件主席", "term": "2025–2026 届"} if index == 1 else None,
                        "card": design["card"], "intro": intro, "tags": ["嵌入式", "开源协作", "从零开始"],
                        "avatar": "", "cover": "", "url": "#", "works": []})
    return render(request, "showcase/demo.html", {"members": members, "palette": palette, "palettes": PALETTES})
