import datetime

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.roles import is_officer
from news.models import Post
from notify.models import Notification
from notify.services import notify_user

from . import bilibili
from .models import Feedback, FeedbackReply, SiteConfig

# 首页图片走廊的槽位顺序。内容、比例、拍摄要求都在 core/slots.py，这里只定顺序。
# 视图刻意不去查 MediaSlot：{% slot %} 自己会取（整表缓存，一次查询覆盖所有槽位）。
GALLERY_SLOT_KEYS = [
    "home.gallery.pcb",
    "home.gallery.group",
    "home.gallery.etched",
    "home.gallery.lab",
    "home.gallery.solder",
    "home.gallery.award",
]


def home(request):
    config = SiteConfig.load()

    stats = bilibili.get_stats(config.bilibili_mid)
    # 精选优先（后台配置 BV 号，封面可控），未配置时回退到最新 3 个投稿
    featured = config.featured_bvid_list
    if featured:
        videos = bilibili.get_videos_by_bvids(featured)
    else:
        videos = bilibili.get_latest_videos(config.bilibili_mid, limit=3)
    recruit_video = bilibili.get_video_info(config.recruit_video_bvid)

    years = datetime.date.today().year - config.founding_year

    latest_posts = list(Post.objects.published().visible_to(request.user)[:3])

    # 分镜 07「作品」。口径走 Project.public()（同一个方法喂作品墙、作品详情、
    # 这里），否则迟早出现「首页展示了一个作品墙上没有的作品」。
    # 一件都没有时整段不渲染 —— 见模板注释，空壳区块比没有这段更糟。
    from projects.models import Project

    featured_works = list(Project.public().filter(is_featured=True)[:3])

    # 分镜 08「荣誉」。口径走 Honor.wall()（和荣誉墙同一个），一项都没有时整段
    # 不渲染。数字同样是数出来的，不是手填的。
    from news.models import Honor

    featured_honors = list(Honor.wall().filter(is_featured=True)[:4])
    honor_summary = Honor.summary() if featured_honors else None

    context = {
        "bili_stats": stats,
        "bili_videos": videos,
        "recruit_video": recruit_video,
        "gallery_slots": GALLERY_SLOT_KEYS,
        "years": years,
        "latest_posts": latest_posts,
        "featured_works": featured_works,
        "featured_honors": featured_honors,
        "honor_summary": honor_summary,
    }
    return render(request, "core/home.html", context)


def recruit(request):
    return render(request, "core/recruit.html")


def privacy(request):
    return render(request, "core/privacy.html")


# ---------------------------------------------------------------- 网站问题反馈

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
        # order_by 显式写：annotate() 会建 GROUP BY，带 GROUP BY 的查询不再套用
        # Meta.ordering（`-created_at`），「我的反馈」就会变成任意顺序 —— 而且这里
        # 还切了前 10 条，取到的是哪 10 条都不确定。
        my_feedbacks = (
            request.user.feedbacks.annotate(reply_count=Count("replies"))
            .order_by("-created_at")[:10]
        )
    return render(request, "core/feedback.html", {"my_feedbacks": my_feedbacks})


def _can_view_feedback(user, fb) -> bool:
    """提交人本人或站务管理可以查看并参与对话。"""
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
            # 管理组回复 -> 站内通知提交人（提交人自己回复不通知自己）
            if fb.user_id and fb.user_id != request.user.pk:
                notify_user(
                    fb.user, f"你的反馈 #{fb.pk} 有新回复",
                    kind=Notification.Kind.FEEDBACK, body=content[:200],
                    url=f"/feedback/{fb.pk}/",
                )
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
