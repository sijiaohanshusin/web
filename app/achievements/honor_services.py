from copy import deepcopy
import hashlib
import json

from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q

from news.models import Honor
from projects.work_services import WorkConflict, lock_owner
from showcase.services import encode_image
from .forms import HonorForm
from .models import Certificate, HonorDraft
from .services import ledger_lock, check_duplicate, validate_people, sync_people


def revoke_ineligible_honors(users, using='default'):
    invalid = users.filter(Q(is_active=False) | Q(member_level__lt=3, is_superuser=False))
    drafts = HonorDraft.objects.using(using).filter(owner_id__in=invalid.values('pk'), published__isnull=False)
    Honor.objects.using(using).filter(pk__in=drafts.values('honor_id')).update(is_public=False)
    drafts.update(published=None, version=F('version') + 1)


def locked(user, pk, version=None):
    owner = lock_owner(user)
    draft = HonorDraft.objects.select_for_update().get(owner=owner, pk=pk)
    if version is not None and draft.version != version:
        raise WorkConflict('版本已变化。当前输入仍保留，请打开新标签页核对后合并。')
    return draft


@transaction.atomic
def create(user):
    owner = lock_owner(user)
    if owner.honor_drafts.count() >= 50:
        raise ValidationError('每人最多保留 50 条荣誉草稿。请清理不用的私有记录。')
    return HonorDraft.objects.create(owner=owner)


def save(user, pk, version, data, upload=None):
    output = encode_image(upload)[0] if upload else None
    written = None
    try:
        with transaction.atomic():
            draft = locked(user, pk, version)
            data = deepcopy(data)
            data.setdefault('show_certificate', bool(data.get('certificate') or upload))
            form = HonorForm(draft, {**data, 'version': version})
            if not form.is_valid():
                raise ValidationError('奖项内容、关联作品或证书无效，请检查后保存。')
            data.update(form.design())
            data['contributors'] = validate_people(data.get('contributors', []))
            if output:
                if draft.images.count() >= 5:
                    raise ValidationError('每条荣誉最多保留 5 张证书，请先移除并删除不用的证书。')
                image = Certificate(draft=draft, width=output[1][0], height=output[1][1], byte_size=len(output[0]))
                image.image.save('certificate.jpg', ContentFile(output[0]), save=False)
                written = image.image.storage, image.image.name
                image.save()
                if data['show_certificate']:
                    data['certificate'] = str(image.pk)
            draft.draft, draft.version = data, draft.version + 1
            draft.save()
            return draft
    except Exception:
        if written:
            written[0].delete(written[1])
        raise


def claims(draft):
    digest = hashlib.sha256(json.dumps(draft.draft, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'pk': str(draft.pk), 'owner': draft.owner_id, 'version': draft.version, 'digest': digest}


def token(draft):
    return signing.dumps(claims(draft), salt='honor-preview')


def projection(draft, honor=None):
    item = honor or Honor(is_member_honor=True, is_public=False)
    for key in ('title', 'contest', 'year', 'level', 'awardee', 'note'):
        setattr(item, key, draft.draft[key])
    item.project_id = draft.draft.get('project')
    image = draft.images.filter(pk=draft.draft['certificate']).first() if draft.draft.get('certificate') else None
    item.certificate = image.image.name if image else ''
    item.cert_w, item.cert_h = (image.width, image.height) if image else (None, None)
    return item


@transaction.atomic
def publish(user, pk, preview_token, consent):
    if consent != 'on':
        raise ValidationError('请确认互联网公开范围及共同参与者的署名同意。')
    draft = locked(user, pk)
    try:
        valid = signing.loads(preview_token, salt='honor-preview', max_age=1200)
    except signing.BadSignature:
        raise ValidationError('预览凭证已失效，请重新预览。')
    if valid != claims(draft):
        raise WorkConflict('草稿已变化，请重新预览后发布。')
    form = HonorForm(draft, {**draft.draft, 'version': draft.version})
    if not form.is_valid():
        raise ValidationError('关联作品或证书已失效，请返回编辑页处理。')
    ledger_lock()
    item = projection(draft, draft.honor)
    check_duplicate(item)
    item.is_public = True
    item.save()
    sync_people(item, draft.draft.get('contributors', []))
    draft.honor, draft.published, draft.version = item, deepcopy(draft.draft), draft.version + 1
    draft.save()
    return draft


@transaction.atomic
def withdraw(user, pk, version):
    draft = locked(user, pk, version)
    ledger_lock()
    if draft.honor_id:
        Honor.objects.filter(pk=draft.honor_id).update(is_public=False, is_featured=False)
    draft.published, draft.version = None, draft.version + 1
    draft.save()


@transaction.atomic
def remove_image(user, pk, version, image_pk):
    draft = locked(user, pk, version)
    image = draft.images.get(pk=image_pk)
    if str(image.pk) in {draft.draft.get('certificate'), (draft.published or {}).get('certificate')}:
        raise ValidationError('证书仍被草稿或公开版本引用。请先保存移除引用并更新公开版本，或撤回。')
    storage, name = image.image.storage, image.image.name
    image.delete()
    draft.version += 1
    draft.save()
    transaction.on_commit(lambda: storage.delete(name))


@transaction.atomic
def remove(user, pk, version):
    draft = locked(user, pk, version)
    ledger_lock()
    if draft.published:
        raise ValidationError('请先撤回再删除。')
    # Preserve claimed historical records; withdrawal is sufficient to stop publication.
    if draft.honor_id and (draft.honor.contributors.filter(user__isnull=False).exists() or draft.honor.claim_set.exists()):
        raise ValidationError('已有成员关联或认领记录，不能直接删除档案；撤回后不会公开，请联系站务处理争议。')
    files = [(image.image.storage, image.image.name) for image in draft.images.all()]
    honor = draft.honor
    draft.delete()
    if honor:
        honor.delete()
    transaction.on_commit(lambda: [storage.delete(name) for storage, name in files])
