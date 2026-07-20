import datetime

from django.conf import settings
from django.core.cache import cache

from .models import SiteConfig


def _recruitment_open() -> bool:
    """是否有正在进行的招新（缓存 5 分钟，供导航条条件显示「招新」入口）。"""
    flag = cache.get("recruit:open")
    if flag is None:
        from recruitment.models import Campaign

        flag = any(c.is_open for c in Campaign.objects.filter(is_active=True))
        cache.set("recruit:open", flag, 300)
    return flag


def site(request):
    """向所有模板注入站点配置与当前年份（页脚版权等使用）。"""
    return {
        "site_config": SiteConfig.load(),
        "current_year": datetime.date.today().year,
        "forum_url": settings.FORUM_URL,
        "recruitment_open": _recruitment_open(),
    }
