import io
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from accounts.models import Position, User
from showcase.services import add_asset, change, get_showcase, preview_ticket


class Command(BaseCommand):
    help = "Create fictional members for local-only browser regression checks."

    def handle(self, **options):
        if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Demo seeding is restricted to local DEBUG + SQLite.")
        names = ["林序", "陈知远", "苏禾", "很长昵称也应该拥有完整且清晰的身份信息", "无头像成员", "周屿"]
        for index, name in enumerate(names):
            user, created = User.objects.get_or_create(username=f"demo-showcase-{index}", defaults={"real_name": f"虚构测试成员{index}", "member_level": 3, "grade": str(2025-index%3), "specialty": "software" if index % 2 else "hardware"})
            if not created:
                continue
            user.set_password("LocalDemo-Only-2026!")
            user.save()
            if index in {1, 5}:
                user.position = Position.objects.get(name="硬件副主席")
                user.position_term_start = 2025
                user.save()
                if index == 5:
                    user.position = None
                    user.save()
            sc = get_showcase(user)
            data = sc.draft
            data["nickname"] = name
            data["card"]["template"] = ["plate", "gallery", "type"][index % 3]
            data["page"]["template"] = ["plate", "gallery", "type"][index % 3]
            data["card"]["palette"] = ["cyan", "copper", "silver"][index % 3]
            data["content"].update(intro="保持好奇，让每一次尝试都有回响。" if index%3==2 else "把一个想法，从纸上的电路变成桌上的作品。", about="这是虚构测试成员的自我介绍。\n\n热爱动手，乐于分享，也愿意从新的领域重新开始。", tags=["嵌入式", "开源协作", "摄影"], skills="硬件设计 / Python / 文档整理")
            if index == 1:
                image = Image.new("RGB", (1200, 900), "#133239")
                draw = ImageDraw.Draw(image)
                for x in range(80, 1200, 70):
                    draw.line((x, 0, x, 900), fill="#29515a", width=1)
                for x in range(240, 900, 90):
                    draw.line((x, 0, x, 260, 1100-x, 620, 1100-x, 900), fill="#9ddcce", width=6)
                    draw.ellipse((x-12, 210, x+12, 234), outline="#d2a571", width=5)
                draw.rounded_rectangle((430, 300, 760, 590), radius=12, fill="#142028", outline="#efb77a", width=8)
                out = io.BytesIO()
                image.save(out, "PNG")
                asset = add_asset(user, SimpleUploadedFile("demo.png", out.getvalue(), content_type="image/png"))
                data["content"]["cover"] = str(asset.pk)
                data["content"]["works"] = [{"title": "一块会发光的实验板", "description": "从原理图开始，记录一次完整的设计迭代。", "image": str(asset.pk), "url": "", "project": ""}]
            if index == 5:
                data["page"]["modules"].append("history")
            change(user, "publish", sc.revision, data, True, preview_ticket(sc, data))
        self.stdout.write("Local fictional showcases ready. Login: demo-showcase-0 / LocalDemo-Only-2026!")
