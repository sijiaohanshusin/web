"""Create only isolated, fictional editor acceptance data; never a production seed."""
from pathlib import Path
import uuid

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Position, User
from showcase.schema import empty_design
from showcase.services import add_asset, change, get_showcase


class Command(BaseCommand):
    help = "Prepare a private fictional showcase editor on local DEBUG + SQLite."

    def handle(self, **options):
        if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Editor fixtures require local DEBUG + SQLite.")
        user, created = User.objects.get_or_create(username="showcase-review", defaults={
            "real_name": "虚构测试成员", "member_level": 3, "grade": "2024", "specialty": "hardware",
        })
        if not created:
            self.stdout.write("Existing acceptance account preserved; no drafts overwritten.")
            return
        user.set_password("LocalReview-Only-2026!")
        user.position = Position.objects.get(name="硬件副主席")
        user.position_term_start = 2025
        user.save()
        sc = get_showcase(user)
        photos = {}
        for name in ("maker", "soldering", "signal", "builder"):
            path = Path(__file__).resolve().parents[2] / "demo_assets" / (name + ".png")
            photos[name] = str(add_asset(user, SimpleUploadedFile(name + ".png", path.read_bytes(), content_type="image/png")).pk)
        design = empty_design()
        design.update(nickname="陈知远", cohort="2024", direction="hardware")
        design["card"].update(template="gallery", modules=["intro", "work", "tags"], texture="none")
        design["card"]["background"].update(mode="photo", image=photos["maker"], y=45)
        design["page"].update(template="gallery", modules=["intro", "skills", "works", "gallery", "links", "history", "medals"])
        design["content"].update(
            avatar=photos["maker"], cover=photos["soldering"], intro="从原理图，到第一声回应。",
            about="把一个想法变成真实的电路，是我最喜欢的过程。\n\n在实验室里焊接、调试，也在每一次尝试中学习。我相信好的作品不仅能运行，还能被清楚地理解和分享。",
            skills="嵌入式开发 / 电路设计 / 开源硬件\n正在学习：信号处理与交互装置",
            tags=["嵌入式", "开源硬件"],
            works=[
                {"id": str(uuid.uuid4()), "title": "桌面信号发生器", "description": "从原理图到固件，记录一件桌面仪器的设计与调试。", "image": photos["signal"], "url": "", "project": ""},
                {"id": str(uuid.uuid4()), "title": "开放式实验板", "description": "让每次新的尝试，都有一个可靠的起点。", "image": photos["soldering"], "url": "", "project": ""},
            ],
            gallery=[{"image": photos["builder"], "caption": "专注于把事情做好。"}, {"image": photos["maker"], "caption": "从一块电路板开始。"}],
            links=[{"label": "协会网站", "url": "https://heuesta.cn/"}],
        )
        design["card"]["featured_work"] = design["content"]["works"][0]["id"]
        change(user, "save", sc.revision, design)
        self.stdout.write("Private local fixture ready. Login: showcase-review / LocalReview-Only-2026!")
