# -*- coding: utf-8 -*-
"""素材槽模板标签。

用法：
    {% load slots %}
    {% slot "home.gallery.group" %}
    {% slot "home.gallery.group" class="nf-tile" ratio="16 / 9" %}

渲染三种状态：
    有片段 —— <video muted loop playsinline> + 封面帧（仅 kind="video" 的槽位）
    有图   —— <img> + 图注，尺寸与焦点都来自数据库
    缺图   —— 设计过的「空焊盘」占位框：虚线 + 四角定位标 + 拍摄要求，
              站务登录时多一个直达上传的入口

视频槽是图片槽的**超集**：`image` 字段身份变成封面帧。只上传封面时它就是一张
静态图，`prefers-reduced-motion` 下也是显示这一帧 —— 不必为降级另备素材。
`<video>` 标签上刻意**不写 `autoplay`**，播放由 video-slots.js 按能力决定
（省流模式、reduced-motion 都只显示封面），JS 挂了就停在封面，不会白屏。

为什么缺图要做成一个设计过的状态，而不是隐藏或者放一张占位图：
  1. 协会现在确实缺图，这会持续一段时间。缺图是常态，常态就该有正式设计。
  2. 隐藏会让版面在补图前后完全变样，等于要排两次版。
  3. 随便找张图凑数是在骗自己 —— 上线前没人记得哪些是凑的。占位框把「这里
     缺一张什么样的照片」明确写出来，反而更容易被补上。

`ratio` 一般不用传，登记表里已经写了；只有同一个槽位在两个地方按不同比例
出现时才覆盖。
"""
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

from core import slots as registry
from core.models import MediaSlot

register = template.Library()


def _upload_url(key: str) -> str | None:
    """驾驶舱素材中心的直达链接，还没有这个页面时返回 None。

    素材中心是 Task 8 的内容。这里刻意不硬编码 URL，也不假装它已经存在：
    reverse 不通就不显示入口，等那个页面落地后自动亮起来。
    """
    try:
        return f"{reverse('dashboard:media_slots')}?key={key}"
    except NoReverseMatch:
        return None


@register.inclusion_tag("includes/slot.html", takes_context=True)
def slot(context, key, ratio=None, css_class="", eager=False, show_cta=True,
         fallback_url=""):
    """渲染一个素材槽。

    参数
    ----
    key           core/slots.py 里登记的标识
    ratio         覆盖登记表里的 aspect-ratio，通常不需要
    css_class     额外的 class，拼在 .slot 后面（模板里写 class="..."）
    eager         True 则不加 loading="lazy"。首屏可见的图才需要，
                  其余一律懒加载
    show_cta      是否显示站务专属的上传入口。素材中心自己用这个标签做预览，
                  那里每张卡片旁边就是上传表单，占位框里再来一个链接是噪音
    fallback_url  运行时兜底图的 URL，例如从 B 站接口拿到的封面。
                  优先级排在登记表的静态 fallback 之后：静态那份是仓库里
                  钉死的自有素材，运行时这份是碰运气拿到的（B 站限流就没了）

    取用优先级：数据库片段 → 数据库封面 → 登记表静态兜底 → 运行时兜底 → 空焊盘
    """
    spec = registry.get(key)
    if spec is None:
        # 拼错的 key 在开发期必须炸出来，否则会以「那个位置什么都没有」的形式
        # 一路混到线上，而那和「还没拍」看起来一模一样。
        if settings.DEBUG:
            raise template.TemplateSyntaxError(
                f"素材槽 {key!r} 没有在 core/slots.py 登记。"
                "拼错了，或者忘了加登记项。"
            )
        spec = registry.placeholder_spec(key)

    filled = MediaSlot.load_all().get(key)
    static_fallback = static(spec.fallback) if spec.fallback else ""

    return {
        "spec": spec,
        "obj": filled,
        # 视频槽只有真的传了片段才走 <video>。只传封面时它就是一张静态图 ——
        # 视频槽是图片槽的超集，不需要为「还没剪好片子」单独准备降级素材。
        "sources": filled.video_sources if (filled and spec.kind == registry.VIDEO) else [],
        "src": (filled.image.url if filled else (static_fallback or fallback_url)),
        "width": filled.width if filled else None,
        "height": filled.height if filled else None,
        "alt": (filled.alt if filled and filled.alt else spec.label),
        "caption": filled.caption if filled else "",
        "credit": filled.credit if filled else "",
        "object_position": filled.object_position if filled else "50% 50%",
        "ratio": ratio or spec.ratio,
        "css_class": css_class,
        "loading": "eager" if eager else "lazy",
        "is_officer": show_cta and getattr(context.get("user"), "is_officer", False),
        "upload_url": _upload_url(key),
    }
