from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.roles import is_officer
from achievements.forms import people_set, people_data
from . import work_services as services
from .member_forms import WorkForm, WorkRankingForm
from .models import MemberWork, Project, WorkImage, can_publish_work, current_work_year


def author_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_publish_work(request.user):
            raise PermissionDenied('已激活的科协会员及以上可以提交作品。')
        return view(request, *args, **kwargs)
    return wrapped


def owned(request, pk):
    return get_object_or_404(MemberWork.objects.select_related('owner', 'project'), pk=pk, owner=request.user)


def problem(request, exc, work=None):
    return render(request, 'projects/work_problem.html', {'error': ' '.join(exc.messages), 'work': work},
                  status=409 if isinstance(exc, services.WorkConflict) else 400)


def request_version(request):
    try:
        return int(request.POST['version'])
    except (ValueError, KeyError):
        raise ValidationError('操作版本无效，请重新打开作品。')


@author_required
@require_GET
def mine(request):
    items = MemberWork.objects.filter(owner=request.user).select_related('project', 'owner')
    return render(request, 'projects/my_works.html', {'page': Paginator(items, 12).get_page(request.GET.get('page'))})


@author_required
@require_POST
def create(request):
    try:
        work = services.create_work(request.user)
    except ValidationError as exc:
        return problem(request, exc)
    return redirect('works:edit', pk=work.pk)


@author_required
@require_http_methods(['GET', 'POST'])
def edit(request, pk):
    work = owned(request, pk)
    people = people_set(request.POST if request.method == 'POST' else None, work.draft.get('contributors', []))
    status = 200
    if request.method == 'POST':
        form = WorkForm(work, request.POST, request.FILES)
        valid, people_valid = form.is_valid(), not people.is_bound or people.is_valid()
        if valid and people_valid:
            try:
                data = {**form.design(), 'contributors': people_data(people, work.draft.get('contributors', []))}
                work = services.save_work(request.user, work.pk, form.cleaned_data['version'], data, form.cleaned_data['upload'])
                messages.success(request, '草稿已保存。已有公开版本不会自动改变。')
                return redirect('works:preview' if request.POST.get('action') == 'preview' else 'works:edit', pk=work.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
                if isinstance(exc, services.WorkConflict):
                    status = 409
    else:
        form = WorkForm(work, initial={'year': current_work_year(), 'department': 'other', **work.draft, 'version': work.version})
    return render(request, 'projects/work_editor.html', {'work': work, 'form': form, 'images': work.images.all(),
                                                        'people': people, 'conflict': status == 409}, status=status)


@author_required
@require_GET
def preview(request, pk):
    work = owned(request, pk)
    form = WorkForm(work, {**work.draft, 'version': work.version})
    if not form.is_valid():
        messages.error(request, '请先补全名称、年份、方向和公开署名，再预览。')
        return redirect('works:edit', pk=pk)
    return render(request, 'projects/work_preview.html', {
        'work': work, 'project': services.project_from_draft(work),
        'shots': work.images.filter(pk__in=work.draft.get('gallery', [])),
        'preview': True, 'publish_token': services.preview_token(work),
        'contributors': work.draft.get('contributors', []),
    })


@author_required
@require_POST
def publish(request, pk):
    work = owned(request, pk)
    try:
        work = services.publish_work(request.user, pk, request.POST.get('token', ''), request.POST.get('consent'))
    except ValidationError as exc:
        return problem(request, exc, work)
    messages.success(request, '作品已发布到协会作品墙，无需等待站务审核。')
    return redirect(work.project.public_url)


@author_required
@require_POST
def withdraw(request, pk):
    work = owned(request, pk)
    try:
        if request.POST.get('confirm') != 'on':
            raise ValidationError('请先确认撤回。')
        services.withdraw_work(request.user, pk, request_version(request))
    except ValidationError as exc:
        return problem(request, exc, work)
    messages.success(request, '作品已撤回，草稿仍保留；他人之前下载的内容无法收回。')
    return redirect('works:edit', pk=pk)


@author_required
@require_POST
def remove_image(request, pk, image_pk):
    work = owned(request, pk)
    get_object_or_404(WorkImage, pk=image_pk, work=work)
    try:
        services.delete_image(request.user, pk, image_pk, request_version(request))
    except ValidationError as exc:
        return problem(request, exc, work)
    messages.success(request, '未引用的图片已删除。')
    return redirect('works:edit', pk=pk)


@author_required
@require_POST
def remove(request, pk):
    work = owned(request, pk)
    try:
        if request.POST.get('confirm') != 'on':
            raise ValidationError('请先确认删除草稿和素材。')
        services.delete_work(request.user, pk, request_version(request))
    except ValidationError as exc:
        return problem(request, exc, work)
    messages.success(request, '作品草稿与素材已删除。')
    return redirect('works:mine')


@require_GET
def image(request, image_pk):
    asset = get_object_or_404(WorkImage.objects.select_related('work__owner', 'work__project'), pk=image_pk)
    work = asset.work
    owner = can_publish_work(request.user) and request.user.pk == work.owner_id
    if not owner and (not work.is_public or str(asset.pk) not in services.image_ids(work.published)):
        raise Http404
    if settings.DEBUG:
        try:
            response = FileResponse(asset.image.open('rb'), content_type='image/jpeg')
        except FileNotFoundError:
            raise Http404
    else:
        response = HttpResponse(content_type='image/jpeg')
        response['X-Accel-Redirect'] = '/protected/' + quote(asset.image.name)
    response['Content-Disposition'] = 'inline; filename="work-image.jpg"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def deny_direct_image(request, path):
    return HttpResponseForbidden('请从作品图片接口访问。')


@login_required
@require_http_methods(['GET', 'POST'])
def ranking(request):
    if not is_officer(request.user):
        raise PermissionDenied
    error = None
    if request.method == 'POST':
        form = WorkRankingForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item = get_object_or_404(Project.public().select_for_update(of=('self',)), pk=form.cleaned_data['project'])
                Project.objects.filter(pk=item.pk).update(importance=form.cleaned_data['importance'], is_featured=form.cleaned_data['is_featured'])
            messages.success(request, '排序设置已保存，未更改作者的内容或公开选择。')
            return redirect('works:ranking')
        error = form.errors
    items = Project.public()
    query = request.GET.get('q', '').strip()[:120]
    if query:
        items = items.filter(name__icontains=query)
    return render(request, 'dashboard/work_ranking.html', {'page': Paginator(items, 20).get_page(request.GET.get('page')),
                                                         'query': query, 'error': error})
