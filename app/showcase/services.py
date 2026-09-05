import hashlib
import io
import json
import re
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import User
from projects.models import Project
from .models import ModerationEvent, Showcase, ShowcaseAsset, eligible
from .schema import empty_design, referenced_assets, validate_design, upgrade_design


class Conflict(Exception):
    pass


def revoke_ineligible(users, using="default"):
    """Called in the same transaction as eligibility changes, including bulk updates."""
    ineligible = users.filter(Q(is_active=False) | Q(member_level__lt=3, is_superuser=False))
    Showcase.objects.using(using).filter(user_id__in=ineligible.values("pk"), published__isnull=False).update(
        published=None, public_name="", public_tags="", public_cohort="", public_direction="",
        published_at=None, revision=F("revision") + 1, withdrawal_reason="展示资格已变化，请恢复资格后重新发布。",
    )


def get_showcase(user):
    draft = empty_design()
    # Do not use username: it can contain an internal identifier.
    draft.update(nickname=user.real_name[:30], cohort=user.grade if user.grade.isdigit() and len(user.grade) == 4 else "",
                 direction=user.specialty, direction_detail=user.specialty_custom[:40])
    return Showcase.objects.get_or_create(user=user, defaults={"draft": draft})[0]


def validate_owned(showcase, raw, publishing=False):
    data = validate_design(raw, publishing=publishing)
    refs = referenced_assets(data)
    if set(str(pk) for pk in showcase.assets.filter(pk__in=refs).values_list("pk", flat=True)) != refs:
        raise ValidationError({"assets": ["有图片不属于你的素材库，或已被删除，请重新选择。"]})
    projects = {w["project"] for w in data["content"]["works"] if w["project"]}
    if projects != set(str(pk) for pk in Project.public().filter(pk__in=projects).values_list("pk", flat=True)):
        raise ValidationError({"content.works": ["只能关联已公开的站内作品，请移除已转为私密的关联。"]})
    return data


def digest(data):
    return hashlib.sha256(json.dumps(upgrade_design(data), sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def preview_ticket(showcase, data, scope="both"):
    return signing.dumps({"user": showcase.user_id, "revision": showcase.revision, "hash": digest(data), "scope": scope}, salt="member-showcase-preview")


@transaction.atomic
def change(user, action, revision, raw=None, consent=False, ticket=""):
    if not isinstance(action, str) or action not in {"save", "publish", "withdraw"}:
        raise ValidationError("不支持的操作。")
    # One lock order everywhere: account, showcase, assets. This also serializes deactivation.
    current = User.objects.select_for_update().get(pk=user.pk)
    if action != "withdraw" and not eligible(current):
        raise PermissionDenied("已激活的科协会员及以上才可设计和发布展示。")
    if eligible(current):
        get_showcase(current)
    elif not Showcase.objects.filter(user=current).exists():
        raise ValidationError("没有可撤回的展示。")
    sc = Showcase.objects.select_for_update().get(user=current)
    if type(revision) is not int or revision != sc.revision:
        raise Conflict("另一页面已保存或展示状态已变化。请保留当前内容并刷新后对照，未覆盖任何内容。")
    if action != "withdraw" and not eligible(current):
        raise PermissionDenied("已激活的科协会员及以上才可设计和发布展示。")
    if action in {"save", "publish"}:
        data = validate_owned(sc, raw, publishing=action == "publish")
        if action == "publish":
            if sc.blocked:
                raise PermissionDenied("展示已被管理员下架，请联系管理员解除限制后再发布。")
            if consent is not True:
                raise ValidationError("请确认互联网公开说明。")
            try:
                if not isinstance(ticket, str):
                    raise signing.BadSignature
                claim = signing.loads(ticket, salt="member-showcase-preview", max_age=3600)
            except signing.BadSignature:
                raise ValidationError("请先预览当前设计，再发布。")
            scope = claim.get("scope") if isinstance(claim, dict) else None
            if scope not in ({"both"} if data["publication"]["page"] else {"card", "both"}):
                raise ValidationError("请先预览本次要公开的全部内容。")
            if claim != {"user": current.pk, "revision": revision, "hash": digest(data), "scope": scope}:
                raise ValidationError("设计已变化，请先预览最新内容。")
            sc.published = data
            sc.public_name = data["nickname"]
            # Only tags actually enabled on a public card are searchable.
            tags_visible = (
                "tags" in data["card"]["modules"]
                or (data["publication"]["page"] and "skills" in data["page"]["modules"])
            )
            sc.public_tags = " ".join(data["content"]["tags"]) if tags_visible else ""
            sc.public_cohort = data["cohort"]
            sc.public_direction = data["direction"]
            sc.published_at = timezone.now()
            sc.withdrawal_reason = ""
        sc.draft = data
    elif action == "withdraw":
        sc.published = None
        sc.public_name = sc.public_tags = sc.public_cohort = sc.public_direction = ""
        sc.published_at = None
        sc.withdrawal_reason = "你已撤回公开展示。"
    else:
        raise ValidationError("不支持的操作。")
    sc.revision += 1
    sc.save()
    # A rollback to the old UI must never republish a withdrawn/renamed showcase.
    User.objects.filter(pk=current.pk).update(show_on_team=False)
    return sc


@transaction.atomic
def moderate(actor, showcase_id, action, reason):
    if not actor.is_active or not actor.is_officer:
        raise PermissionDenied
    if action not in {"hide", "unlock"} or not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValidationError("请填写下架或解除限制的原因（最多 500 字）。")
    uid = Showcase.objects.values_list("user_id", flat=True).get(pk=showcase_id)
    User.objects.select_for_update().get(pk=uid)
    sc = Showcase.objects.select_for_update().get(pk=showcase_id)
    sc.blocked = action == "hide"
    sc.moderation_reason = reason.strip()
    # Unlock is not consent and must not restore a publication.
    sc.published = None
    sc.public_tags = sc.public_cohort = sc.public_direction = ""
    sc.published_at = None
    sc.withdrawal_reason = "管理员已解除限制，请自行重新发布。" if action == "unlock" else "展示已被管理员下架。"
    sc.revision += 1
    sc.save()
    User.objects.filter(pk=uid).update(show_on_team=False)
    ModerationEvent.objects.create(showcase=sc, actor=actor, action=action, reason=reason.strip())
    return sc


def encode_image(upload):
    if getattr(upload, "size", 0) > 5 * 1024 * 1024:
        raise ValidationError("单张图片不能超过 5MB。")
    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValidationError("单张图片不能超过 5MB。")
    suffix = Path(upload.name).suffix.lower()
    formats = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(io.BytesIO(raw))
            if source.format not in formats or suffix not in formats[source.format]:
                raise ValidationError("仅接受真实的静态 JPEG、PNG、WebP 图片，扩展名必须匹配。")
            if source.width * source.height > 8_000_000 or getattr(source, "n_frames", 1) != 1:
                raise ValidationError("图片不得超过 800 万像素，且不能是动画。")
            source.verify()
            source = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
            source.load()
            outputs = []
            for maximum in (1600, 640):
                resized = source.copy()
                resized.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
                # Rebuild pixels to discard EXIF, comments, profiles and other metadata.
                clean = Image.new("RGB", resized.size)
                clean.paste(resized)
                buf = io.BytesIO()
                clean.save(buf, "JPEG", quality=86, optimize=True)
                outputs.append((buf.getvalue(), clean.size))
            return outputs
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("图片损坏或无法安全解码，请换一张静态图片。")


def add_asset(user, upload):
    outputs = encode_image(upload)
    written = []
    try:
        with transaction.atomic():
            current = User.objects.select_for_update().get(pk=user.pk)
            if not eligible(current):
                raise PermissionDenied
            sc = Showcase.objects.select_for_update().get(user=current)
            if sc.assets.count() >= 20:
                raise ValidationError("每人最多 20 张素材，请先删除未使用的图片。")
            name = str(getattr(upload, "name", "图片")).replace("\\", "/").split("/")[-1]
            name = re.sub(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", "", name)
            asset = ShowcaseAsset(showcase=sc, width=outputs[0][1][0], height=outputs[0][1][1],
                                  display_name=(Path(name).stem[:110] or "图片") + ".jpg", byte_size=len(outputs[0][0]))
            for field, output, suffix in ((asset.image, outputs[0], "large"), (asset.thumbnail, outputs[1], "small")):
                field.save(f"{sc.pk}/{asset.pk}-{suffix}.jpg", ContentFile(output[0]), save=False)
                written.append((field.storage, field.name))
            asset.save()
            return asset
    except Exception:
        for storage, name in written:
            storage.delete(name)
        raise


@transaction.atomic
def delete_asset(user, asset_id):
    User.objects.select_for_update().get(pk=user.pk)
    sc = Showcase.objects.select_for_update().get(user=user)
    asset = sc.assets.get(pk=asset_id)
    if str(asset.pk) in referenced_assets(sc.draft) or (sc.published and str(asset.pk) in referenced_assets(sc.published)):
        raise ValidationError("图片仍被草稿或已发布设计引用，请先移除引用并保存。")
    files = [(field.storage, field.name) for field in (asset.image, asset.thumbnail)]
    asset.delete()
    transaction.on_commit(lambda: [storage.delete(name) for storage, name in files])
