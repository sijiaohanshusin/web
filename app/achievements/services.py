import unicodedata
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.roles import is_officer
from news.models import Honor
from projects.models import Project
from .models import Claim, Contributor, LedgerLock


def ledger_lock():
    LedgerLock.objects.get_or_create(pk=1)
    LedgerLock.objects.select_for_update().get(pk=1)


def target(kind, pk, public=True):
    if kind == 'work':
        query = Project.public() if public else Project.objects.all()
    elif kind == 'honor':
        query = Honor.objects.public() if public else Honor.objects.all()
    else:
        raise ValidationError('成果类型无效。')
    item = query.filter(pk=pk).first()
    if not item:
        raise ValidationError('记录不存在或已撤回，请返回成果中心。')
    return item


def relation(item):
    return {'project': item} if isinstance(item, Project) else {'honor': item}


def normalize(value):
    return ''.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def check_duplicate(item):
    # Similar titles are hints, not proof. Only identical year/title/team blocks publication.
    work = isinstance(item, Project)
    fields = ('name', 'work_year', 'public_credit') if work else ('title', 'year', 'contest', 'level', 'awardee')
    signature = tuple(normalize(getattr(item, key)) for key in fields)
    for row in type(item).objects.exclude(pk=item.pk).values('pk', *fields):
        if tuple(normalize(row[key]) for key in fields) == signature:
            raise ValidationError('已有同年份、同名称、同团队署名的记录（奖项同时核对赛事与级别）。请在成果中心认领或联系原维护人，不要重复发布；确属不同团队请准确填写团队署名。')


def validate_people(rows):
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValidationError('参与成员最多 20 人。')
    clean, ids, users = [], set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError('参与成员格式无效。')
        name, role, cohort, username = [str(row.get(k) or '').strip() for k in ('name', 'role', 'cohort', 'username')]
        if not name or len(name) > 60 or len(role) > 60:
            raise ValidationError('每位参与者需要 1–60 字公开署名，分工最多 60 字。')
        if cohort and (not cohort.isascii() or not cohort.isdigit() or len(cohort) != 4 or not 1995 <= int(cohort) <= timezone.localdate().year):
            raise ValidationError('参与者入学届别应为 1995 至当前年份的四位年份，未知可留空。')
        try:
            key = str(uuid.UUID(str(row.get('id')))) if row.get('id') else str(uuid.uuid4())
        except ValueError:
            raise ValidationError('参与者编号无效。')
        if key in ids:
            raise ValidationError('同一参与者不能重复添加。')
        ids.add(key)
        account = None
        if username:
            account = get_user_model().objects.filter(username=username, is_active=True).first()
            if not account:
                raise ValidationError(f'没有找到可关联的用户名「{username[:60]}」。尚未注册时请留空，日后认领。')
            if account.pk in users:
                raise ValidationError('同一注册账号不能重复添加。')
            users.add(account.pk)
        clean.append({'id': key, 'name': name, 'role': role, 'cohort': cohort, 'username': username,
                      'account': account.pk if account else None})
    return clean


def sync_people(item, rows):
    rows = validate_people(rows)
    existing = {str(c.pk): c for c in item.contributors.all()}
    kept = []
    for index, row in enumerate(rows):
        person = existing.get(row['id'])
        if person and not person.from_submission:
            raise ValidationError('核验补录的署名不能通过作者草稿改写，请联系站务处理更正。')
        if person and person.user_id:
            if (person.name, person.role, person.cohort) != (row['name'], row['role'], row['cohort']):
                raise ValidationError('已确认的参与者不能被改名或改为另一个人。请联系站务核验更正。')
            if row['account'] and row['account'] != person.user_id:
                raise ValidationError('不能把已确认的署名转给另一个账号。')
        if not person:
            if Contributor.objects.filter(pk=row['id']).exists():
                raise ValidationError('参与者编号不属于这条成果。')
            person = Contributor(pk=row['id'], from_submission=True, **relation(item))
        person.name, person.role, person.cohort = row['name'], row['role'], row['cohort']
        if not person.user_id:
            if person.invited_user_id != row['account']:
                person.invitation_declined = False
            person.invited_user_id = row['account']
        person.active, person.position = True, index
        person.save()
        kept.append(person.pk)
    # Claims added after publication are independent of the owner's older draft.
    for pk, person in existing.items():
        if person.from_submission and person.pk not in kept:
            person.active = False
            person.save(update_fields=['active'])


def active_user(user):
    if not user.is_authenticated or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists():
        raise PermissionDenied


@transaction.atomic
def request_claim(user, kind, pk, contributor_id, public_name, role, evidence):
    active_user(user)
    ledger_lock()
    item = target(kind, pk)
    public_name, role, evidence = public_name.strip(), role.strip(), evidence.strip()
    if not public_name or len(public_name) > 60 or len(role) > 60 or not evidence or len(evidence) > 2000:
        raise ValidationError('请填写公开署名和核验说明，说明最多 2000 字。不要提交密码、学号或证件照片。')
    person = None
    if contributor_id:
        person = item.contributors.filter(pk=contributor_id, active=True).first()
        if not person or person.user_id or (person.invited_user_id and person.invited_user_id != user.pk):
            raise ValidationError('这条署名已经关联或不允许认领，请联系站务核验。')
    if item.contributors.filter(user=user, active=True).exists():
        raise ValidationError('你已经关联此成果，不必重复认领。')
    claim, _ = Claim.objects.get_or_create(applicant=user, **relation(item), defaults={
        'public_name': public_name, 'role': role, 'evidence': evidence,
    })
    if claim.status == Claim.Status.APPROVED:
        raise ValidationError('该申请已完成，请联系站务处理更正。')
    claim.contributor, claim.public_name, claim.role, claim.evidence = person, public_name, role, evidence
    claim.status, claim.reason, claim.reviewer, claim.reviewed_at = Claim.Status.PENDING, '', None, None
    claim.save()
    return claim


@transaction.atomic
def review_claim(user, pk, decision, reason):
    if not is_officer(get_user_model().objects.get(pk=user.pk)):
        raise PermissionDenied
    ledger_lock()
    claim = Claim.objects.select_related('applicant').get(pk=pk)
    if claim.applicant_id == user.pk:
        raise PermissionDenied('不能审核自己的认领申请。')
    if claim.status != Claim.Status.PENDING or decision not in ('approved', 'rejected') or not reason.strip() or len(reason) > 500:
        raise ValidationError('仅可核验待处理申请，需填写 1–500 字处理说明。')
    item = target('work' if claim.project_id else 'honor', claim.project_id or claim.honor_id)
    if decision == 'approved':
        active_user(claim.applicant)
        person = claim.contributor
        if person and (not person.active or person.user_id or (person.invited_user_id and person.invited_user_id != claim.applicant_id)):
            raise ValidationError('署名状态已变化，不能覆盖其他人的关联。')
        if item.contributors.filter(user=claim.applicant, active=True).exists():
            raise ValidationError('该成员已关联此成果。')
        person = person or Contributor(**relation(item), name=claim.public_name, role=claim.role, position=item.contributors.count())
        person.user, person.invited_user = claim.applicant, None
        person.save()
        claim.contributor = person
    claim.status, claim.reviewer, claim.reason, claim.reviewed_at = decision, user, reason.strip(), timezone.now()
    claim.save()
    return claim


@transaction.atomic
def respond_invitation(user, pk, accept):
    active_user(user)
    ledger_lock()
    person = Contributor.objects.get(pk=pk)
    if not person.active or person.invitation_declined or person.invited_user_id != user.pk or person.user_id:
        raise PermissionDenied
    item = target(person.kind, person.target_id)
    if accept and item.contributors.filter(user=user, active=True).exists():
        raise ValidationError('你已经关联此成果，请勿重复确认。')
    person.user = user if accept else None
    if accept:
        person.invited_user = None
    person.invitation_declined = not accept
    person.save()
