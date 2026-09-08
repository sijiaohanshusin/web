from urllib.parse import quote

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.roles import is_officer
from news.models import Honor
from projects.models import Project, can_publish_work, current_work_year
from projects.member_views import author_required, request_version
from projects.work_services import WorkConflict
from . import services, honor_services
from .forms import ClaimForm, HonorForm, people_set, people_data
from .models import Contributor, Claim, HonorDraft, Certificate


def public_people():
    return Contributor.objects.filter(active=True).filter(
        Q(project_id__in=Project.public().values('pk')) | Q(honor_id__in=Honor.objects.public().values('pk'))
    ).select_related('project', 'honor')


@author_required
@require_GET
def people_lookup(request):
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.utils import timezone
    key = f'achievement-lookup:{request.user.pk}:{int(timezone.now().timestamp()) // 60}'
    if cache.add(key, 1, timeout=120):
        count = 1
    else:
        count = cache.incr(key)
    if count > 60:
        return JsonResponse({'usernames': []}, status=429)
    query = request.GET.get('q', '').strip()[:150]
    values = [] if len(query) < 2 else list(get_user_model().objects.filter(is_active=True, username__icontains=query).order_by('username').values_list('username', flat=True)[:12])
    return JsonResponse({'usernames': values})


def card(kind, item):
    work = kind == 'work'
    return {'kind': kind, 'pk': item.pk, 'title': item.name if work else item.title,
            'year': item.work_year if work else item.year, 'credit': item.public_credit if work else item.awardee,
            'url': item.public_url, 'label': '作品' if work else '荣誉'}


def problem(request, exc):
    return render(request, 'achievements/problem.html', {'error': ' '.join(exc.messages)}, status=409 if isinstance(exc, WorkConflict) else 400)


@login_required
@require_GET
def hub(request):
    credits = public_people().filter(user=request.user)
    invitations = public_people().filter(invited_user=request.user, user__isnull=True, invitation_declined=False)
    claims = request.user.achievement_claims.select_related('project', 'honor')
    return render(request, 'achievements/hub.html', {'credits': credits, 'invitations': invitations,
        'claims': Paginator(claims, 12).get_page(request.GET.get('page')), 'can_create': can_publish_work(request.user)})


@login_required
@require_GET
def catalog(request):
    query = request.GET.get('q', '').strip()[:120]
    kind = request.GET.get('kind', '')
    year = request.GET.get('year', '')
    works, honors = Project.public(), Honor.objects.public()
    if query:
        works = works.filter(Q(name__icontains=query) | Q(public_credit__icontains=query) | Q(contributors__active=True, contributors__name__icontains=query)).distinct()
        honors = honors.filter(Q(title__icontains=query) | Q(contest__icontains=query) | Q(awardee__icontains=query) | Q(contributors__active=True, contributors__name__icontains=query)).distinct()
    if year.isascii() and year.isdigit() and len(year) == 4:
        works, honors = works.filter(work_year=int(year)), honors.filter(year=int(year))
    items = ([] if kind == 'honor' else [card('work', p) for p in works]) + ([] if kind == 'work' else [card('honor', h) for h in honors])
    items.sort(key=lambda i: (-i['year'], i['title'], i['kind'], i['pk']))
    return render(request, 'achievements/catalog.html', {'page': Paginator(items, 20).get_page(request.GET.get('page')),
                                                        'query': query, 'kind': kind, 'year': year})


@login_required
@require_http_methods(['GET', 'POST'])
def record(request, kind, pk):
    try:
        item = services.target(kind, pk)
    except ValidationError:
        raise Http404
    form = ClaimForm(item, request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            c = form.cleaned_data
            services.request_claim(request.user, kind, pk, c['contributor'].pk if c['contributor'] else None,
                                   c['public_name'], c['role'], c['evidence'])
            messages.success(request, '认领申请已提交。核验结果可在成果中心查看，不会自动新增作品或奖项。')
            return redirect('achievements:hub')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'achievements/record.html', {'item': card(kind, item), 'people': item.contributors.filter(active=True), 'form': form})


@login_required
@require_POST
def invitation(request, pk):
    get_object_or_404(Contributor, pk=pk, invited_user=request.user)
    if request.POST.get('decision') not in ('accept', 'decline'):
        return HttpResponse(status=400)
    try:
        services.respond_invitation(request.user, pk, request.POST['decision'] == 'accept')
    except ValidationError as exc:
        return problem(request, exc)
    messages.success(request, '参与关联已确认。' if request.POST['decision'] == 'accept' else '已拒绝账号关联，原公开署名未被改写；署名有误请反馈站务。')
    return redirect('achievements:hub')


@login_required
@require_POST
def cancel_claim(request, pk):
    with transaction.atomic():
        services.ledger_lock()
        claim = get_object_or_404(Claim, pk=pk, applicant=request.user, status=Claim.Status.PENDING)
        claim.status = Claim.Status.CANCELLED
        claim.save()
    messages.success(request, '认领申请已取消。')
    return redirect('achievements:hub')


@login_required
@require_http_methods(['GET', 'POST'])
def review(request):
    if not is_officer(request.user):
        raise PermissionDenied
    error = None
    if request.method == 'POST':
        claim_id = request.POST.get('claim', '')
        if not claim_id.isascii() or not claim_id.isdigit():
            return HttpResponse(status=400)
        claim = get_object_or_404(Claim, pk=int(claim_id))
        if claim.applicant_id == request.user.pk:
            messages.warning(request, '不能核验自己的认领申请，请另一位站务人员核验。申请状态未改变，无需重复提交。')
            return redirect('achievements:review')
        try:
            services.review_claim(request.user, int(claim_id), request.POST.get('decision'), request.POST.get('reason', ''))
            messages.success(request, '核验结果已保存。未改变会员等级、项目权限或原奖项数量。')
            return redirect('achievements:review')
        except ValidationError as exc:
            error = ' '.join(exc.messages)
    status = request.GET.get('status', 'pending')
    if status not in Claim.Status.values:
        status = 'pending'
    items = Claim.objects.filter(status=status).select_related('applicant', 'project', 'honor', 'contributor')
    return render(request, 'dashboard/achievement_review.html', {'page': Paginator(items, 20).get_page(request.GET.get('page')),
                                                               'error': error, 'status': status, 'states': Claim.Status.choices})


def owned(request, pk):
    return get_object_or_404(HonorDraft.objects.select_related('honor', 'owner'), pk=pk, owner=request.user)


@author_required
@require_GET
def honors_mine(request):
    return render(request, 'achievements/honors.html', {'page': Paginator(request.user.honor_drafts.select_related('honor'), 12).get_page(request.GET.get('page'))})


@author_required
@require_POST
def honor_create(request):
    try:
        draft = honor_services.create(request.user)
    except ValidationError as exc:
        return problem(request, exc)
    return redirect('achievements:honor_edit', pk=draft.pk)


@author_required
@require_http_methods(['GET', 'POST'])
def honor_edit(request, pk):
    draft = owned(request, pk)
    posted = request.POST if request.method == 'POST' else None
    form = HonorForm(draft, posted, request.FILES or None, initial={**draft.draft, 'version': draft.version})
    people = people_set(posted, draft.draft.get('contributors', []))
    status = 200
    if posted is not None:
        valid, people_valid = form.is_valid(), not people.is_bound or people.is_valid()
        if valid and people_valid:
            try:
                data = {**form.design(), 'contributors': people_data(people, draft.draft.get('contributors', []))}
                honor_services.save(request.user, pk, form.cleaned_data['version'], data, form.cleaned_data['upload'])
                messages.success(request, '荣誉草稿已保存，公开版本未改变。')
                return redirect('achievements:honor_preview' if posted.get('action') == 'preview' else 'achievements:honor_edit', pk=pk)
            except ValidationError as exc:
                form.add_error(None, exc)
                status = 409 if isinstance(exc, WorkConflict) else 200
    from . import recognition
    ai_reason = recognition.available()
    return render(request, 'achievements/honor_editor.html', {'draft': draft, 'form': form, 'people': people,
        'images': draft.images.all(), 'conflict': status == 409, 'ai_enabled': not ai_reason,
        'ai_notice': recognition.ERRORS.get(ai_reason, '')}, status=status)


@author_required
@require_GET
def honor_preview(request, pk):
    draft = owned(request, pk)
    form = HonorForm(draft, {**draft.draft, 'version': draft.version})
    if not form.is_valid():
        messages.error(request, '请先保存完整的奖项资料。')
        return redirect('achievements:honor_edit', pk=pk)
    return render(request, 'achievements/honor_preview.html', {'draft': draft, 'honor': honor_services.projection(draft),
        'people': draft.draft.get('contributors', []), 'token': honor_services.token(draft)})


@author_required
@require_POST
def honor_publish(request, pk):
    owned(request, pk)
    try:
        draft = honor_services.publish(request.user, pk, request.POST.get('token', ''), request.POST.get('consent'))
    except ValidationError as exc:
        return problem(request, exc)
    messages.success(request, '荣誉已发布到协会荣誉墙。首页精选仍由站务设置。')
    return redirect(draft.honor.public_url)


@author_required
@require_POST
def honor_withdraw(request, pk):
    owned(request, pk)
    try:
        if request.POST.get('confirm') != 'on':
            raise ValidationError('请确认撤回。')
        honor_services.withdraw(request.user, pk, request_version(request))
    except ValidationError as exc:
        return problem(request, exc)
    messages.success(request, '荣誉已撤回，草稿和认领记录保留。')
    return redirect('achievements:honor_edit', pk=pk)


@author_required
@require_POST
def honor_delete(request, pk):
    owned(request, pk)
    try:
        if request.POST.get('confirm') != 'on':
            raise ValidationError('请确认删除。')
        honor_services.remove(request.user, pk, request_version(request))
    except ValidationError as exc:
        return problem(request, exc)
    messages.success(request, '未公开草稿与证书已删除。')
    return redirect('achievements:honors')


@author_required
@require_POST
def certificate_delete(request, pk, image_pk):
    draft = owned(request, pk)
    get_object_or_404(Certificate, pk=image_pk, draft=draft)
    try:
        honor_services.remove_image(request.user, pk, request_version(request), image_pk)
    except ValidationError as exc:
        return problem(request, exc)
    return redirect('achievements:honor_edit', pk=pk)


@require_GET
def certificate(request, pk):
    image = get_object_or_404(Certificate.objects.select_related('draft'), pk=pk)
    draft = image.draft
    owner = can_publish_work(request.user) and request.user.pk == draft.owner_id
    public = draft.published and draft.published.get('certificate') == str(image.pk) and Honor.objects.public().filter(pk=draft.honor_id).exists()
    if not owner and not public:
        raise Http404
    if settings.DEBUG:
        try:
            response = FileResponse(image.image.open('rb'), content_type='image/jpeg')
        except FileNotFoundError:
            raise Http404
    else:
        response = HttpResponse(content_type='image/jpeg')
        response['X-Accel-Redirect'] = '/protected/' + quote(image.image.name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline; filename="certificate.jpg"'
    return response


class RankingForm(forms.Form):
    honor = forms.IntegerField(min_value=1)
    importance = forms.IntegerField(min_value=0, max_value=100)
    is_featured = forms.BooleanField(required=False)


@login_required
@require_http_methods(['GET', 'POST'])
def honor_ranking(request):
    if not is_officer(request.user):
        raise PermissionDenied
    error = None
    if request.method == 'POST':
        form = RankingForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                services.ledger_lock()
                item = get_object_or_404(Honor.objects.public(), pk=form.cleaned_data['honor'])
                Honor.objects.filter(pk=item.pk).update(importance=form.cleaned_data['importance'], is_featured=form.cleaned_data['is_featured'])
            messages.success(request, '排序已更新。成员的公开选择和内容没有改变。')
            return redirect('achievements:honor_ranking')
        error = form.errors
    return render(request, 'dashboard/honor_ranking.html', {'page': Paginator(Honor.objects.public(), 20).get_page(request.GET.get('page')), 'error': error})
