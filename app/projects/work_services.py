from copy import deepcopy
import hashlib
import json

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from showcase.services import encode_image
from .member_forms import WorkForm
from .models import MemberWork, Project, WorkImage, can_publish_work


class WorkConflict(ValidationError):
    pass


def revoke_ineligible_works(users, using='default'):
    # Run inside the user update transaction; use persisted eligibility, not a stale instance.
    from django.db.models import F, Q
    ineligible = users.filter(Q(is_active=False) | Q(member_level__lt=3, is_superuser=False))
    works = MemberWork.objects.using(using).filter(owner_id__in=ineligible.values('pk'), published__isnull=False)
    Project.objects.using(using).filter(pk__in=works.values('project_id')).update(is_public=False)
    works.update(published=None, version=F('version') + 1)


def image_ids(data):
    if not data:
        return set()
    return set(filter(None, [data.get('cover'), *data.get('gallery', [])]))


def lock_owner(user):
    current = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    if not can_publish_work(current):
        raise PermissionDenied
    return current


def locked_work(user, pk, version=None):
    owner = lock_owner(user)
    work = MemberWork.objects.select_for_update().get(pk=pk, owner=owner)
    if version is not None and work.version != version:
        raise WorkConflict('其他标签页已更新此作品。当前输入已保留，请先对照最新版本，勿覆盖保存。')
    return work


@transaction.atomic
def create_work(user):
    owner = lock_owner(user)
    if MemberWork.objects.filter(owner=owner).count() >= 30:
        raise ValidationError('最多保存 30 件作品，请先删除不需要的私有草稿。')
    return MemberWork.objects.create(owner=owner)


def save_work(user, pk, version, data, upload=None):
    from achievements.services import validate_people
    data = deepcopy(data)
    data['contributors'] = validate_people(data.get('contributors', []))
    output = encode_image(upload)[0] if upload else None
    written = None
    try:
        with transaction.atomic():
            work = locked_work(user, pk, version)
            if work.images.filter(pk__in=image_ids(data)).count() != len(image_ids(data)):
                raise ValidationError('选择的图片已删除或不属于这件作品，请重新选择。')
            if output:
                if work.images.count() >= 20:
                    raise ValidationError('每件作品最多保留 20 张图片，请先清理未引用的素材。')
                image = WorkImage(work=work, width=output[1][0], height=output[1][1], byte_size=len(output[0]))
                image.image.save('upload.jpg', ContentFile(output[0]), save=False)
                written = (image.image.storage, image.image.name)
                image.save()
                if not data.get('cover'):
                    data['cover'] = str(image.pk)
                elif len(data['gallery']) < 6:
                    data['gallery'].append(str(image.pk))
            work.draft = data
            work.version += 1
            work.save(update_fields=['draft', 'version', 'updated_at'])
            return work
    except Exception:
        if written:
            written[0].delete(written[1])
        raise


def draft_fingerprint(work):
    return hashlib.sha256(json.dumps(work.draft, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preview_token(work):
    return signing.dumps({'work': str(work.pk), 'owner': work.owner_id, 'version': work.version,
                          'draft': draft_fingerprint(work)}, salt='member-work-preview')


def project_from_draft(work, project=None):
    data = work.draft
    project = project or Project(is_member_work=True, created_by=work.owner)
    for key in ('name', 'summary', 'highlight', 'department', 'tags', 'external_url'):
        setattr(project, key, data.get(key, ''))
    project.work_year = data['year']
    project.public_credit = data['credit']
    cover = work.images.filter(pk=data['cover']).first() if data.get('cover') else None
    project.cover = cover.image.name if cover else ''
    project.cover_w, project.cover_h = (cover.width, cover.height) if cover else (None, None)
    return project


@transaction.atomic
def publish_work(user, pk, token, consent):
    from achievements.services import ledger_lock, check_duplicate, sync_people
    if consent != 'on':
        raise ValidationError('请先确认图文、署名和链接可以面向互联网公开。')
    try:
        claims = signing.loads(token, salt='member-work-preview', max_age=1200)
    except signing.BadSignature:
        raise ValidationError('预览确认已失效，请重新预览后发布。')
    work = locked_work(user, pk)
    if claims != {'work': str(work.pk), 'owner': user.pk, 'version': work.version, 'draft': draft_fingerprint(work)}:
        raise WorkConflict('草稿已变化，请重新预览当前版本后再发布。')
    form = WorkForm(work, {**work.draft, 'version': work.version})
    if not form.is_valid():
        raise ValidationError('作品内容或图片已失效，请返回编辑页检查。')
    ledger_lock()
    project = Project.objects.select_for_update().get(pk=work.project_id) if work.project_id else None
    project = project_from_draft(work, project)
    check_duplicate(project)
    project.is_public = True
    project.save()
    sync_people(project, work.draft.get('contributors', []))
    work.project = project
    work.published = deepcopy(work.draft)
    work.version += 1
    work.save()
    return work


@transaction.atomic
def withdraw_work(user, pk, version):
    work = locked_work(user, pk, version)
    from achievements.services import ledger_lock
    ledger_lock()
    if work.project_id:
        Project.objects.filter(pk=work.project_id).update(is_public=False)
    work.published = None
    work.version += 1
    work.save()
    return work


@transaction.atomic
def delete_image(user, pk, image_pk, version):
    work = locked_work(user, pk, version)
    image = WorkImage.objects.get(pk=image_pk, work=work)
    if str(image.pk) in image_ids(work.draft) | image_ids(work.published):
        raise ValidationError('图片仍被草稿或公开版本使用。先保存移除引用，再更新公开版本或撤回。')
    storage, name = image.image.storage, image.image.name
    image.delete()
    work.version += 1
    work.save(update_fields=['version', 'updated_at'])
    transaction.on_commit(lambda: storage.delete(name))


@transaction.atomic
def delete_work(user, pk, version):
    work = locked_work(user, pk, version)
    from achievements.services import ledger_lock
    ledger_lock()
    if work.project_id and (work.project.contributors.filter(user__isnull=False).exists() or work.project.claim_set.exists() or work.project.honors.exists()):
        raise ValidationError('已有成员关联、认领或奖项记录，请保留撤回的档案并联系站务处理，不直接删除。')
    if work.published or (work.project_id and work.project.is_public):
        raise ValidationError('请先撤回公开作品，再删除草稿。')
    files = [(image.image.storage, image.image.name) for image in work.images.all()]
    project_id = work.project_id
    work.delete()
    if project_id:
        Project.objects.filter(pk=project_id, is_member_work=True).delete()
    transaction.on_commit(lambda: [storage.delete(name) for storage, name in files])
