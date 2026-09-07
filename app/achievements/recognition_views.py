from datetime import timedelta

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET

from projects.member_views import author_required, request_version
from projects.work_services import WorkConflict
from .models import Certificate, RecognitionTask
from .views import owned
from . import recognition


def error(exc):
    if isinstance(exc, recognition.RecognitionError):
        return JsonResponse({'error': str(exc), 'code': exc.code}, status=429 if exc.code == 'limit' else 503)
    return JsonResponse({'error': ' '.join(exc.messages)}, status=409 if isinstance(exc, WorkConflict) else 400)


@never_cache
@author_required
@require_POST
def upload(request, pk):
    owned(request, pk)
    try:
        image, version = recognition.upload_certificate(request.user, pk, request_version(request), request.FILES.get('upload'))
    except ValidationError as exc:
        return error(exc)
    return JsonResponse({'version': version, 'image': {'id': str(image.pk), 'url': image.public_url,
        'label': str(image), 'width': image.width, 'height': image.height}}, status=201)


def serialize(task):
    return {'id': str(task.pk), 'status': task.status,
        'status_url': reverse('achievements:recognition_status', args=[task.pk]),
        'error': recognition.ERRORS.get(task.error_code, ''),
        'result': task.result if task.status == 'succeeded' else {},
        'matches': recognition.public_matches(task.result.get('fields', {})) if task.status == 'succeeded' else []}


@never_cache
@author_required
@require_POST
def start(request, pk):
    draft = owned(request, pk)
    try:
        image = get_object_or_404(Certificate, pk=request.POST.get('image'), draft=draft)
        task = recognition.start(image, request.POST.get('consent'))
    except (recognition.RecognitionError, ValidationError) as exc:
        return error(exc)
    return JsonResponse(serialize(task), status=202)


@never_cache
@author_required
@require_GET
def status(request, pk):
    task = get_object_or_404(RecognitionTask, pk=pk, certificate__draft__owner=request.user)
    if task.created_at < timezone.now() - timedelta(hours=24):
        task.status, task.result, task.error_code = 'expired', {}, 'result_expired'
    return JsonResponse(serialize(task))
