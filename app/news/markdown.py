"""Markdown 渲染 + XSS 消毒。公告、活动详情等富文本统一走这里。"""
import re

import markdown as md
import nh3
from django.utils.safestring import mark_safe

_EXTENSIONS = [
    "extra",       # 表格、围栏代码块、脚注、定义列表等
    "sane_lists",
    "nl2br",       # 单个换行即 <br>，与论坛的书写习惯一致
]

# nh3 的默认白名单**不放 id 和 class**，于是 markdown 生成的脚注锚点会被整套剥掉：
# 正文里的 `<sup><a href="#fn:1">` 还在，而它要跳的 `<li id="fn:1">` 上的 id 没了 ——
# **点脚注跳不动，返回链接也跳不动**，而页面照常渲染、控制台干净。
# 所以按标签定点放开：只在需要锚点的那几个标签上允许 id，class 只允许在 div 上
# （脚注容器 `<div class="footnote">` 靠它才能被样式认出来）。
#
# 允许 id 的代价是内容作者能造出重复 id 或与站内 id 撞名（比如 id="main"）。
# 这些正文只有站务能写，且 nh3 仍然剥掉脚本与事件属性，所以这个交换是划算的；
# 真正危险的 `on*`、`style`、`srcset` 一个都没放。
_ATTRIBUTES = {tag: set(attrs) for tag, attrs in nh3.ALLOWED_ATTRIBUTES.items()}
for _tag in ("a", "li", "sup", "h1", "h2", "h3", "h4", "h5", "h6"):
    _ATTRIBUTES.setdefault(_tag, set()).add("id")
_ATTRIBUTES.setdefault("div", set()).add("class")

# 「只有一张图的段落」→ <figure> + <figcaption>。
# markdown 把 `![说明](图)` 渲染成 `<p><img alt="说明"></p>`，**alt 里那句说明一个字
# 都不显示** —— 而图注是长文里独立的一层信息（这张图在讲什么）。所以在消毒之后把
# 这种段落升级成 figure，说明文字取 alt。
# 只处理「整段就是一张图」的情况：段落里还有别的文字时说明该由那段文字承担，
# 硬塞一个 figcaption 会把同一句话说两遍。
_LONE_IMG = re.compile(r"<p>\s*(<img\b[^>]*>)\s*</p>")
_ALT = re.compile(r'\balt="([^"]*)"')


def _figures(html: str) -> str:
    def one(m: "re.Match[str]") -> str:
        img = m.group(1)
        alt = _ALT.search(img)
        caption = alt.group(1).strip() if alt else ""
        if not caption:
            return f"<figure>{img}</figure>"
        return f"<figure>{img}<figcaption>{caption}</figcaption></figure>"

    return _LONE_IMG.sub(one, html)


def render_markdown(text: str) -> str:
    """渲染 Markdown 为安全 HTML（nh3 白名单消毒，脚本/事件属性一律剥掉）。"""
    if not text:
        return ""
    html = md.markdown(text, extensions=_EXTENSIONS, output_format="html")
    # 顺序要紧：**先消毒再升级 figure**。反过来的话 figure/figcaption 是我们自己
    # 生成的标签，却要再过一遍消毒器，而 alt 里的内容此时还没被转义。
    clean = nh3.clean(html, attributes=_ATTRIBUTES)
    return mark_safe(_figures(clean))
