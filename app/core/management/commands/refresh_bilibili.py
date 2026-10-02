from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from core import bilibili
from core.models import SiteConfig


class Command(BaseCommand):
    help = "Refresh last-good Bilibili snapshots without blocking page requests."

    def handle(self, *args, **options):
        config = SiteConfig.load()
        jobs = [(f"bili:stats:{config.bilibili_mid}", lambda: bilibili.get_stats(config.bilibili_mid, refresh=True))]
        if not config.featured_bvid_list:
            jobs.append((f"bili:videos:{config.bilibili_mid}:3", lambda: bilibili.get_latest_videos(config.bilibili_mid, limit=3, refresh=True)))
        for bvid in dict.fromkeys([config.recruit_video_bvid, *config.featured_bvid_list]):
            if bvid:
                jobs.append((f"bili:video:{bvid}", lambda value=bvid: bilibili.get_video_info(value, refresh=True)))
        failed = []
        for key, refresh in jobs:
            before = cache.get(key + ":refreshed")
            refresh()
            if cache.get(key + ":refreshed") == before:
                failed.append(key)
        if failed:
            raise CommandError("Refresh failed; last-good snapshots retained: " + ", ".join(failed))
        self.stdout.write(self.style.SUCCESS(f"Refreshed {len(jobs)} Bilibili snapshots."))
