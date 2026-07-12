import datetime

from .models import SiteConfig


def site(request):
    """向所有模板注入站点配置与当前年份（页脚版权等使用）。"""
    return {
        "site_config": SiteConfig.load(),
        "current_year": datetime.date.today().year,
    }
