"""Markdown 渲染 + XSS 消毒。公告、活动详情等富文本统一走这里。"""
import markdown as md
import nh3
from django.utils.safestring import mark_safe

_EXTENSIONS = [
    "extra",       # 表格、围栏代码块、脚注等
    "sane_lists",
    "nl2br",       # 单个换行即 <br>，与论坛的书写习惯一致
]


def render_markdown(text: str) -> str:
    """渲染 Markdown 为安全 HTML（nh3 白名单消毒，脚本/事件属性一律剥掉）。"""
    if not text:
        return ""
    html = md.markdown(text, extensions=_EXTENSIONS, output_format="html")
    return mark_safe(nh3.clean(html))
