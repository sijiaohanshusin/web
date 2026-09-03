"""Preserve only already-public fields; do not infer new consent."""
import copy
import io
import uuid
import warnings
from PIL import Image, ImageOps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def migrate_members(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Showcase = apps.get_model("showcase", "Showcase")
    Asset = apps.get_model("showcase", "ShowcaseAsset")
    Award = apps.get_model("accounts", "UserMedal")
    db = schema_editor.connection.alias
    storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    candidates = User.objects.using(db).filter(is_active=True, show_on_team=True, position__isnull=False).filter(Q(member_level__gte=3) | Q(is_superuser=True))
    for user in candidates.iterator():
        if Showcase.objects.using(db).filter(user_id=user.pk).exists():
            continue
        style = {"template": "plate", "palette": "cyan", "texture": "grid", "focus": "center", "avatar_shape": "square", "modules": ["intro"]}
        data = {
            "version": 1, "nickname": (user.real_name or user.username)[:30], "cohort": user.grade if user.grade.isdigit() and len(user.grade) == 4 else "",
            "direction": user.specialty, "direction_detail": user.specialty_custom[:40],
            "card": copy.deepcopy(style), "page": copy.deepcopy(style),
            "content": {"intro": user.public_bio[:60], "about": user.public_bio, "tags": [], "skills": "", "avatar": "", "cover": "", "works": [], "gallery": [], "links": []},
        }
        sc = Showcase.objects.using(db).create(user_id=user.pk, draft=data)
        if user.avatar:
            try:
                with storage.open(str(user.avatar), "rb") as file:
                    raw = file.read(5 * 1024 * 1024 + 1)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    source = Image.open(io.BytesIO(raw))
                    if len(raw) > 5 * 1024 * 1024 or source.width * source.height > 8_000_000 or source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                        raise ValueError("Unsupported legacy image")
                    source = ImageOps.exif_transpose(source).convert("RGB")
                    paths = []
                    aid = uuid.uuid4()
                    dimensions = None
                    for name, bound in (("large", 1600), ("small", 640)):
                        resized = source.copy()
                        resized.thumbnail((bound, bound), Image.Resampling.LANCZOS)
                        dimensions = dimensions or resized.size
                        clean = Image.new("RGB", resized.size)
                        clean.paste(resized)
                        buffer = io.BytesIO()
                        clean.save(buffer, "JPEG", quality=86)
                        paths.append(storage.save(f"showcase/{sc.pk}/{aid}-{name}.jpg", ContentFile(buffer.getvalue())))
                    Asset.objects.using(db).create(id=aid, showcase_id=sc.pk, image=paths[0], thumbnail=paths[1], width=dimensions[0], height=dimensions[1])
                    data["content"]["avatar"] = str(aid)
            except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                pass  # Broken old images stay absent; text and prior consent survive.
        sc.draft = copy.deepcopy(data)
        published = copy.deepcopy(data)
        published["legacy_medals"] = list(Award.objects.using(db).filter(user_id=user.pk).order_by("-created_at").values_list("medal__name", flat=True)[:3])
        sc.published = published
        sc.public_name = data["nickname"]
        sc.public_cohort = data["cohort"]
        sc.public_direction = data["direction"]
        sc.published_at = timezone.now()
        sc.save(using=db)
    # Retire the old switch after copying consent into the new snapshot. Old app
    # rollback shows an empty wall rather than exposing withdrawn modern content.
    User.objects.using(db).filter(show_on_team=True).update(show_on_team=False)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_alter_user_managers"), ("showcase", "0001_initial")]
    operations = [migrations.RunPython(migrate_members, migrations.RunPython.noop)]
