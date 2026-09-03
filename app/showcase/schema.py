"""Versioned, closed content schema. No presentation code or remote media is accepted."""
import copy
import math
import re
import uuid
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils import timezone

TEMPLATES = {"plate": "工程铭牌", "gallery": "作品橱窗", "type": "文字档案"}
PALETTES = {"cyan": "信号青", "copper": "焊锡铜", "silver": "银白"}
TEXTURES = {"grid": "坐标网格", "lines": "精密刻线", "none": "纯净基板"}
FOCUS = {"center": "居中", "top": "上方", "bottom": "下方", "left": "左侧", "right": "右侧"}
SHAPES = {"square": "圆角方形", "round": "圆形"}
CARD_MODULES = {"intro": "短介绍", "tags": "技能标签", "work": "精选作品"}
PAGE_MODULES = {"intro": "自我介绍", "skills": "技能兴趣", "works": "作品", "gallery": "图片集", "links": "外部链接", "history": "官方任职经历", "medals": "官方勋章"}
DIRECTIONS = {"hardware": "硬件", "software": "软件", "custom": "自定义"}
BACKGROUNDS = {"gradient": "设计师渐变", "photo": "我的工作照", "solid": "纯色"}
PRESETS = {"graphite": "深海石墨", "copper": "暖铜微光", "ivory": "米白青灰"}
BLURS = {"none": "无模糊", "soft": "轻微模糊", "medium": "柔和模糊"}
MASKS = {"balanced": "均衡", "deep": "深色", "strong": "强遮罩"}


def default_background():
    return {"mode": "gradient", "preset": "graphite", "image": "", "x": 50, "y": 50,
            "zoom": 1, "blur": "none", "mask": "balanced"}


def upgrade_design(raw):
    """Read old snapshots without changing stored content or publication consent."""
    data = copy.deepcopy(raw)
    if isinstance(data, dict) and type(data.get("version")) is int and data["version"] == 1:
        card = obj(data.get("card"), ("template", "palette", "texture", "focus", "avatar_shape", "modules"), "设计")
        background = default_background()
        background["preset"] = "copper" if card["palette"] == "copper" else "graphite"
        content = data.get("content")
        if isinstance(content, dict) and card["template"] == "gallery" and content.get("cover"):
            background.update(mode="photo", image=data["content"]["cover"])
            background.update({"top": {"y": 0}, "bottom": {"y": 100}, "left": {"x": 0}, "right": {"x": 100}}.get(card["focus"], {}))
        card["background"] = background
        data["version"] = 2
    return data


def empty_design():
    return {
        "version": 2, "nickname": "", "cohort": "", "direction": "hardware", "direction_detail": "",
        "card": {"template": "plate", "palette": "cyan", "texture": "grid", "focus": "center", "avatar_shape": "round", "modules": ["intro", "tags"], "background": default_background()},
        "page": {"template": "plate", "palette": "cyan", "texture": "grid", "focus": "center", "avatar_shape": "square", "modules": ["intro", "skills", "works"]},
        "content": {"intro": "", "about": "", "tags": [], "skills": "", "avatar": "", "cover": "", "works": [], "gallery": [], "links": []},
    }


def fail(message):
    raise ValidationError(message)


def obj(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        fail(f"{label}结构不正确，请刷新编辑器后重试。")
    return value


def text(value, limit, label):
    if not isinstance(value, str) or len(value) > limit:
        fail(f"{label}最多 {limit} 字。")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]", value):
        fail(f"{label}包含不支持的控制字符。")
    return value.strip()


def sequence(value, limit, label):
    if not isinstance(value, list) or len(value) > limit:
        fail(f"{label}最多 {limit} 项。")
    return value


def asset_id(value):
    if value == "":
        return value
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        fail("图片标识不正确。")


def https_url(value):
    value = text(value, 600, "链接")
    if not value:
        return ""
    try:
        URLValidator(schemes=["https"])(value)
        parsed = urlsplit(value)
        if parsed.username or parsed.password or any(c.isspace() for c in value):
            fail("链接不得包含账号密码或空白字符。")
    except (ValidationError, ValueError):
        fail("外部链接必须是完整的 HTTPS 地址。")
    return value


def validate_design(raw, *, publishing=False):
    data = upgrade_design(raw)
    defaults = empty_design()
    obj(data, defaults, "展示")
    if type(data["version"]) is not int or data["version"] != 2:
        fail("不支持的展示版本，请刷新页面。")
    data["nickname"] = text(data["nickname"], 30, "公开昵称")
    if publishing and not data["nickname"]:
        fail("发布前请填写公开昵称。")
    if data["nickname"] in {"主席", "硬件主席", "软件主席", "硬件副主席", "软件副主席", "站务管理", "系统管理员", "科协官方"}:
        fail("请使用个人昵称；官方职位由系统单独显示，不能作为昵称。")
    if not isinstance(data["cohort"], str) or (data["cohort"] and data["cohort"] not in {str(y) for y in range(1995, timezone.localdate().year + 1)}):
        fail("请选择有效的四位入学年份。")
    if not isinstance(data["direction"], str) or data["direction"] not in DIRECTIONS:
        fail("请选择有效方向。")
    data["direction_detail"] = text(data["direction_detail"], 40, "公开方向说明")
    for target, modules, maximum in (("card", CARD_MODULES, 3), ("page", PAGE_MODULES, 8)):
        design = obj(data[target], defaults[target], "设计")
        for key, choices in (("template", TEMPLATES), ("palette", PALETTES), ("texture", TEXTURES), ("focus", FOCUS), ("avatar_shape", SHAPES)):
            if not isinstance(design[key], str) or design[key] not in choices:
                fail("请选择编辑器提供的模板与样式。")
        chosen = sequence(design["modules"], maximum, "内容模块")
        if any(not isinstance(m, str) or m not in modules for m in chosen) or len(set(chosen)) != len(chosen):
            fail("模块类型无效或重复。")
    background = obj(data["card"]["background"], default_background(), "卡片背景")
    for key, choices in (("mode", BACKGROUNDS), ("preset", PRESETS), ("blur", BLURS), ("mask", MASKS)):
        if not isinstance(background[key], str) or background[key] not in choices:
            fail("请选择编辑器提供的背景、渐变和遮罩。")
    background["image"] = asset_id(background["image"])
    for key, low, high in (("x", 0, 100), ("y", 0, 100), ("zoom", 1, 1.5)):
        value = background[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            fail("图片焦点或缩放超出允许范围。")
        background[key] = round(value, 2)
    content = obj(data["content"], defaults["content"], "内容")
    for field, limit, label in (("intro", 60, "卡片短介绍"), ("about", 2400, "自我介绍"), ("skills", 600, "技能兴趣")):
        content[field] = text(content[field], limit, label)
    content["tags"] = [text(t, 12, "标签") for t in sequence(content["tags"], 4, "标签")]
    if any(not t for t in content["tags"]) or len(set(content["tags"])) != len(content["tags"]):
        fail("标签不能重复或留空。")
    for key in ("avatar", "cover"):
        content[key] = asset_id(content[key])
    for work in sequence(content["works"], 6, "作品"):
        obj(work, ("title", "description", "image", "url", "project"), "作品")
        work["title"] = text(work["title"], 60, "作品标题")
        work["description"] = text(work["description"], 240, "作品说明")
        work["image"] = asset_id(work["image"])
        work["url"] = https_url(work["url"])
        if not isinstance(work["project"], str) or (work["project"] and not re.fullmatch(r"[1-9][0-9]{0,17}", work["project"])):
            fail("站内作品标识不正确。")
    for item in sequence(content["gallery"], 6, "图片集"):
        obj(item, ("image", "caption"), "图片")
        item["image"] = asset_id(item["image"])
        item["caption"] = text(item["caption"], 100, "图片说明")
    for link in sequence(content["links"], 6, "外部链接"):
        obj(link, ("label", "url"), "链接")
        link["label"] = text(link["label"], 40, "链接名称")
        link["url"] = https_url(link["url"])
    return data


def referenced_assets(data, *, visible_only=False):
    data = upgrade_design(data)
    c = data["content"]
    refs = {c["avatar"]}
    bg = data["card"]["background"]
    if not visible_only or bg["mode"] == "photo":
        refs.add(bg["image"])
    if not visible_only or data["page"]["template"] == "gallery":
        refs.add(c["cover"])
    works = c["works"]
    if not visible_only or "works" in data["page"]["modules"]:
        refs.update(w["image"] for w in works)
    elif "work" in data["card"]["modules"] and works:
        refs.add(works[0]["image"])
    if not visible_only or "gallery" in data["page"]["modules"]:
        refs.update(g["image"] for g in c["gallery"])
    return refs - {""}
