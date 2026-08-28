"""
B 站开放接口集成（只读、带缓存、失败优雅降级）。

- 账号统计：/x/web-interface/card
- 视频列表：/x/series/recArchivesByKeywords
- 视频详情：/x/web-interface/view

所有函数在网络异常 / 接口变更时返回 None 或空列表，页面据此降级显示，
绝不让首页因为 B 站接口挂掉而报错。
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

API_TIMEOUT = 6
CACHE_TTL = 3600  # 1 小时
NEGATIVE_TTL = 300  # 失败短缓存，避免每次请求都打 API

# 请求头是这几个接口能不能通的唯一变量，改动前先看下面的实测记录。
#
# 2026-08-26 在生产服务器与本地同时验证 /x/web-interface/view：
#   Chrome UA + Referer: https://www.bilibili.com/   -> 412 风控拦截
#   requests 默认 UA（python-requests/2.x）           -> 412 风控拦截
#   Chrome UA、不发 Referer                           -> 200
#   自报身份 UA、不发 Referer                          -> 200
#
# 结论：Referer 是触发风控的开关（浏览器 UA + 站内 Referer 但没有 buvid/WBI
# 签名，正是"伪装浏览器"的特征），而默认 UA 在黑名单里。所以这里用一个自报
# 身份的 UA 且不发任何 Referer——既能通，也不假装自己是浏览器。
#
# 注意：模板里引用 B 站图片时仍需 referrerpolicy="no-referrer"，那是浏览器
# 侧的防盗链，与本文件无关。
HEADERS = {
    "User-Agent": "HEU-ESTA-Site/1.0 (+https://heuesta.cn)",
    "Accept": "application/json",
}


def _get_json(url: str, params: dict) -> dict | None:
    if not getattr(settings, "BILIBILI_API_ENABLED", True):
        return None
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=API_TIMEOUT)
        if resp.status_code == 412:
            # 风控拦截。不打 traceback：这是可预期的外部状态，堆栈只会淹没日志。
            # 再次出现说明 B 站又收紧了策略，回到本文件顶部的实测表重新校准请求头。
            logger.warning("bilibili api %s 被风控拦截（412），本次降级展示", url)
            return None
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            logger.warning("bilibili api %s 返回 code=%s", url, data.get("code"))
            return None
        return data.get("data")
    except Exception:  # noqa: BLE001 - 网络问题一律降级
        logger.warning("bilibili api %s 请求失败", url, exc_info=True)
        return None


def _https(url: str) -> str:
    return url.replace("http://", "https://") if url else url


def _format_duration(seconds: int) -> str:
    minutes, sec = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _format_view(view: int) -> str:
    if view >= 10000:
        return f"{view / 10000:.1f}万"
    return str(view)


def get_stats(mid: str) -> dict | None:
    """账号统计：粉丝数、投稿数、获赞数。缓存 1 小时。"""
    cache_key = f"bili:stats:{mid}"
    stats = cache.get(cache_key)
    if stats is not None:
        return stats or None

    data = _get_json("https://api.bilibili.com/x/web-interface/card", {"mid": mid})
    if data is None:
        cache.set(cache_key, {}, NEGATIVE_TTL)
        return None

    stats = {
        "follower": data.get("follower", 0),
        "videos": data.get("archive_count", 0),
        "likes": data.get("like_num", 0),
        "name": (data.get("card") or {}).get("name", ""),
        "face": _https((data.get("card") or {}).get("face", "")),
    }
    cache.set(cache_key, stats, CACHE_TTL)
    return stats


def get_latest_videos(mid: str, limit: int = 6) -> list[dict]:
    """最新投稿视频列表。缓存 1 小时。"""
    cache_key = f"bili:videos:{mid}:{limit}"
    videos = cache.get(cache_key)
    if videos is not None:
        return videos

    data = _get_json(
        "https://api.bilibili.com/x/series/recArchivesByKeywords",
        {"mid": mid, "keywords": "", "ps": limit, "pn": 1},
    )
    if data is None:
        cache.set(cache_key, [], NEGATIVE_TTL)
        return []

    videos = [
        {
            "bvid": item.get("bvid", ""),
            "title": item.get("title", ""),
            "pic": _https(item.get("pic", "")),
            "duration": _format_duration(item.get("duration", 0)),
            "view": _format_view((item.get("stat") or {}).get("view", 0)),
            "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
        }
        for item in (data.get("archives") or [])
    ]
    cache.set(cache_key, videos, CACHE_TTL)
    return videos


def get_video_info(bvid: str) -> dict | None:
    """单个视频信息（标题 + 封面），用于招新视频占位封面。缓存 24 小时。"""
    if not bvid:
        return None
    cache_key = f"bili:video:{bvid}"
    info = cache.get(cache_key)
    if info is not None:
        return info or None

    data = _get_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
    if data is None:
        cache.set(cache_key, {}, NEGATIVE_TTL)
        return None

    info = {
        "bvid": bvid,
        "title": data.get("title", ""),
        "pic": _https(data.get("pic", "")),
        "duration": _format_duration(data.get("duration", 0)),
        "view": _format_view((data.get("stat") or {}).get("view", 0)),
        "url": f"https://www.bilibili.com/video/{bvid}",
    }
    cache.set(cache_key, info, 24 * 3600)
    return info


def get_videos_by_bvids(bvids: list[str]) -> list[dict]:
    """按 BV 号列表取视频（用于首页精选）。取不到的条目跳过。"""
    videos = []
    for bvid in bvids:
        info = get_video_info(bvid)
        if info:
            videos.append(info)
    return videos
