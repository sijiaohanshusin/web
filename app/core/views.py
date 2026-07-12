import datetime

from django.shortcuts import render
from django.templatetags.static import static

from . import bilibili
from .models import CarouselImage, SiteConfig

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
