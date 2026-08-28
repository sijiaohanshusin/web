# -*- coding: utf-8 -*-
"""品牌资源模板标签：把 SVG 内联进页面。

为什么要内联而不是 <img src="...svg">：
  1. `currentColor` 只在内联时生效。导航栏在白区要把会标翻成深色，内联后
     一条 CSS `color` 就够了；用 <img> 就只能上 filter: invert()，那会连带
     影响抗锯齿，而且没法只翻一部分。
  2. 描线动画、脉冲动画要按 path 单独控制，<img> 里的节点 JS 摸不到。
  3. 少一个请求。会标去掉注释后不到 1KB，内联比多一次往返划算。

单一事实来源：几何只存在于 app/static/brand/*.svg。模板、加载动画、
three.js 的 SVGLoader 都读同一个文件，不存在两份坐标漂移的问题。

用法：
    {% load brand %}
    {% inline_svg "brand/logo-mark.svg" class="nav-logo" size=40 %}
    {% inline_svg "brand/logo-mark.svg" class="hero-logo" label="电子科技协会会标" %}

默认是「装饰性」处理（aria-hidden、去掉 <title>），因为多数使用场景旁边
就有文字标签，重复朗读反而吵。需要它自己承担语义时传 label=。
"""
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template import Library
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = Library()

# 生产环境静态文件不会变，读一次缓存住；DEBUG 下每次重读，方便边改边看
_cache: dict[str, str] = {}

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_XMLDECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.S)
_WS_RE = re.compile(r">\s+<")


def _load(path: str) -> str:
    """读取并清理 SVG 源码。返回 <svg ...>...</svg>。"""
    if not settings.DEBUG and path in _cache:
        return _cache[path]

    absolute = finders.find(path)
    if absolute is None:
        raise ValueError(
            f"inline_svg 找不到静态文件 {path!r}。"
            "检查路径是否相对 static/ 根目录，以及文件是否已提交。"
        )
    with open(absolute, encoding="utf-8") as fh:
        markup = fh.read()

    # 注释是给维护者看的，没必要塞进每个页面（会标的注释比图形本身还长）
    markup = _COMMENT_RE.sub("", markup)
    markup = _XMLDECL_RE.sub("", markup)
    markup = _WS_RE.sub("><", markup.strip())

    _cache[path] = markup
    return markup


def _set_attr(svg_tag: str, name: str, value: str) -> str:
    """在 <svg ...> 开标签上设置属性，已存在则替换。"""
    pattern = re.compile(rf'\s{re.escape(name)}="[^"]*"')
    if pattern.search(svg_tag):
        return pattern.sub(f' {name}="{value}"', svg_tag)
    return svg_tag[:-1].rstrip() + f' {name}="{value}"' + svg_tag[-1:]


def _drop_attr(svg_tag: str, name: str) -> str:
    return re.sub(rf'\s{re.escape(name)}="[^"]*"', "", svg_tag)


@register.simple_tag
def inline_svg(path, size=None, label=None, **attrs):
    """内联一个静态目录下的 SVG。

    参数
    ----
    path   相对 static/ 的路径，例如 "brand/logo-mark.svg"
    size   同时设置 width 与 height（像素）。不传则保持文件自身尺寸行为
           （本项目的会标只有 viewBox，会撑满容器，由 CSS 控制大小）
    label  无障碍名称。传了就让 SVG 自己承担语义；不传则视为装饰性，
           加 aria-hidden 并移除 <title>，避免与旁边的文字重复朗读，
           也避免同一页多次内联导致 <title> 的 id 重复。
    attrs  其余属性原样写到 <svg> 上，下划线转连字符（class_ 除外，
           模板里直接写 class= 就行）
    """
    markup = _load(str(path))
    open_tag_match = re.match(r"<svg[^>]*>", markup)
    if not open_tag_match:
        raise ValueError(f"{path!r} 看起来不是合法的 SVG")

    open_tag = open_tag_match.group(0)
    body = markup[open_tag_match.end():]

    if label:
        safe = escape(label)
        # 让 <title> 承担名称。同一页多次带 label 内联会产生重复 id，
        # 所以这里改用 aria-label，既不依赖 id 也不怕重复。
        open_tag = _drop_attr(open_tag, "aria-labelledby")
        open_tag = _set_attr(open_tag, "role", "img")
        open_tag = _set_attr(open_tag, "aria-label", safe)
        body = re.sub(r"<title[^>]*>.*?</title>", "", body, flags=re.S)
    else:
        open_tag = _drop_attr(open_tag, "aria-labelledby")
        open_tag = _drop_attr(open_tag, "role")
        open_tag = _set_attr(open_tag, "aria-hidden", "true")
        open_tag = _set_attr(open_tag, "focusable", "false")
        body = re.sub(r"<title[^>]*>.*?</title>", "", body, flags=re.S)

    if size:
        open_tag = _set_attr(open_tag, "width", str(size))
        open_tag = _set_attr(open_tag, "height", str(size))

    for key, value in attrs.items():
        if value is None or value is False:
            continue
        open_tag = _set_attr(open_tag, key.rstrip("_").replace("_", "-"), escape(str(value)))

    return mark_safe(open_tag + body)
