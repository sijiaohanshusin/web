import datetime

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static

from accounts.roles import is_officer

from . import bilibili
from .models import CarouselImage, Feedback, FeedbackReply, SiteConfig

# 数据库没有轮播图时的兜底走廊：真实素材 + 留白占位格。
# 占位格（kind=placeholder）等照片补齐后，由管理员在后台上传真实图片替换。
FALLBACK_GALLERY = [
    {"kind": "photo", "image_url": "img/carousel/pcb.webp", "title": "PCB 设计与打样", "caption": "从原理图到一块真正的电路板"},
    {"kind": "placeholder", "title": "科协合影", "caption": "这一格，留给 2026 级的你"},
    {"kind": "photo", "image_url": "img/carousel/etched-board.webp", "title": "自制腐蚀板", "caption": "动手做，是科协的传统"},
    {"kind": "placeholder", "title": "实验室日常", "caption": "照片整理中 · 敬请期待"},
    {"kind": "photo", "image_url": "img/carousel/soldering.webp", "title": "焊接实践", "caption": "烙铁与热风枪，亲手搭建电路"},
    {"kind": "placeholder", "title": "电赛获奖合影", "caption": "下一张领奖照，主角是你"},
]


def home(request):
    config = SiteConfig.load()

    stats = bilibili.get_stats(config.bilibili_mid)
    videos = bilibili.get_latest_videos(config.bilibili_mid, limit=6)
    recruit_video = bilibili.get_video_info(config.recruit_video_bvid)

    db_images = list(CarouselImage.objects.filter(is_active=True))
    if db_images:
        gallery = [
            {"kind": "photo", "image_url": item.image.url, "title": item.title, "caption": item.caption}
            for item in db_images
        ]
    else:
        gallery = [
            {**item, "image_url": static(item["image_url"])} if item["kind"] == "photo" else item
            for item in FALLBACK_GALLERY
        ]

    years = datetime.date.today().year - config.founding_year

    context = {
        "bili_stats": stats,
        "bili_videos": videos,
        "recruit_video": recruit_video,
        "gallery": gallery,
        "years": years,
    }
    return render(request, "core/home.html", context)


def recruit(request):
    return render(request, "core/recruit.html")


# ---------------------------------------------------------------- 内测反馈

def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _save_feedback(request) -> tuple[bool, str]:
    """校验+限流+入库。返回 (成功, 提示语)。"""
    content = (request.POST.get("content") or "").strip()
    if len(content) < 5:
        return False, "内容太短了，请描述得具体一点（至少 5 个字）。"
    if len(content) > 2000:
        return False, "内容超长（最多 2000 字），请精简或分多条提交。"

    ip = _client_ip(request)
    if not cache.add(f"fb:cool:{ip}", 1, 30):
        return False, "提交太频繁，请 30 秒后再试。"
    day_key = f"fb:day:{ip}"
    try:
        count = cache.incr(day_key)
    except ValueError:
        cache.set(day_key, 1, 86400)
        count = 1
    if count > 30:
        return False, "今日反馈条数已达上限，感谢热情！明天再来～"

    Feedback.objects.create(
        user=request.user if request.user.is_authenticated else None,
        contact=(request.POST.get("contact") or "").strip()[:100],
        page=(request.POST.get("page") or "").strip()[:300],
        content=content,
    )
    return True, "已收到，感谢反馈！我们会统一审阅处理。"


def feedback(request):
    """独立反馈页（论坛按钮/无 JS 兜底）+ AJAX 提交端点共用。"""
    if request.method == "POST":
        ok, msg = _save_feedback(request)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": ok, "msg": msg}, status=200 if ok else 400)
        (messages.success if ok else messages.error)(request, msg)
        return redirect("core:feedback")

    my_feedbacks = []
    if request.user.is_authenticated:
        my_feedbacks = request.user.feedbacks.annotate(reply_count=Count("replies"))[:10]
    return render(request, "core/feedback.html", {"my_feedbacks": my_feedbacks})


def _can_view_feedback(user, fb) -> bool:
    """提交人本人或干事及以上可以查看/参与对话。"""
    if is_officer(user):
        return True
    return user.is_authenticated and fb.user_id == user.pk


def feedback_detail(request, pk: int):
    """反馈详情：原始内容 + 回复对话，双方可继续回复。"""
    fb = get_object_or_404(
        Feedback.objects.select_related("user", "resolved_by"), pk=pk
    )
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not _can_view_feedback(request.user, fb):
        return HttpResponseForbidden("只有反馈提交人和管理组可以查看该对话。")

    if request.method == "POST":
        content = (request.POST.get("content") or "").strip()
        if len(content) < 2:
            messages.error(request, "回复内容太短。")
        elif len(content) > 2000:
            messages.error(request, "回复内容超长（最多 2000 字）。")
        else:
            FeedbackReply.objects.create(feedback=fb, author=request.user, content=content)
            # 提交人追问已处理的反馈 -> 自动重新打开，管理组会再次看到
            if fb.user_id == request.user.pk and fb.status == Feedback.Status.RESOLVED:
                fb.status = Feedback.Status.PENDING
                fb.save(update_fields=["status"])
                messages.success(request, "回复已发送，该反馈已重新打开。")
            else:
                messages.success(request, "回复已发送。")
        return redirect(request.POST.get("next") or request.path)

    replies = fb.replies.select_related("author", "author__position")
    context = {
        "fb": fb,
        "replies": replies,
        "is_officer_viewer": is_officer(request.user),
    }
    return render(request, "core/feedback_detail.html", context)
