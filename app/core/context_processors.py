import datetime

from django.conf import settings
from django.core.cache import cache

from .models import SiteConfig


# 键名带版本号：缓存里的形状从「一个 bool」变成了「一个 dict」，
# 沿用旧键会让部署后还没过期的旧值被当成 dict 用。
RECRUIT_STATE_KEY = "recruit:state:v1"


def _recruitment_state() -> dict:
    """招新状态（缓存 5 分钟）。

    导航条用它决定要不要显示「招新」入口，首页 CTA 用它做倒计时 —— 同一次查询
    喂两个地方，而且保证两处说法一致。
    """
    state = cache.get(RECRUIT_STATE_KEY)
    if state is None:
        from recruitment.models import Campaign

        campaign = Campaign.current()
        is_open = bool(campaign and campaign.is_open)
        state = {
            "open": is_open,
            "name": campaign.name if campaign else "",
            # 只有「进行中且设了截止时间」才给截止时间：没设截止时间意味着长期
            # 开放，倒计时无从计算，那就干脆不显示，而不是显示一个假的数字。
            "closes_at": campaign.closes_at if (is_open and campaign.closes_at) else None,
        }
        cache.set(RECRUIT_STATE_KEY, state, 300)
    return state


def site(request):
    """向所有模板注入站点配置与当前年份（页脚版权等使用）。"""
    state = _recruitment_state()
    return {
        "site_config": SiteConfig.load(),
        "current_year": datetime.date.today().year,
        "forum_url": settings.FORUM_URL,
        "recruitment_open": state["open"],
        "recruitment_name": state["name"],
        "recruitment_closes_at": state["closes_at"],
    }
