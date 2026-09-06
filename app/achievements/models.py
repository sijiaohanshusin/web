import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse


class LedgerLock(models.Model):
    """Serializes cross-record publication/claim changes without locking public reads."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class Contributor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('projects.Project', null=True, blank=True, on_delete=models.CASCADE, related_name='contributors')
    honor = models.ForeignKey('news.Honor', null=True, blank=True, on_delete=models.CASCADE, related_name='contributors')
    name = models.CharField(max_length=60)
    role = models.CharField(max_length=60, blank=True)
    cohort = models.CharField(max_length=4, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='achievement_credits')
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='achievement_invitations')
    active = models.BooleanField(default=True)
    from_submission = models.BooleanField(default=False)
    invitation_declined = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']
        constraints = [
            models.CheckConstraint(condition=(Q(project__isnull=False, honor__isnull=True) | Q(project__isnull=True, honor__isnull=False)), name='credit_one_record'),
            models.UniqueConstraint(fields=['project', 'user'], condition=Q(user__isnull=False, active=True), name='credit_project_user'),
            models.UniqueConstraint(fields=['honor', 'user'], condition=Q(user__isnull=False, active=True), name='credit_honor_user'),
        ]

    @property
    def kind(self):
        return 'work' if self.project_id else 'honor'

    @property
    def target_id(self):
        return self.project_id or self.honor_id


class Claim(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待核验'
        APPROVED = 'approved', '已关联'
        REJECTED = 'rejected', '未通过'
        CANCELLED = 'cancelled', '已取消'

    project = models.ForeignKey('projects.Project', null=True, blank=True, on_delete=models.CASCADE)
    honor = models.ForeignKey('news.Honor', null=True, blank=True, on_delete=models.CASCADE)
    contributor = models.ForeignKey(Contributor, null=True, blank=True, on_delete=models.SET_NULL)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='achievement_claims')
    public_name = models.CharField(max_length=60)
    role = models.CharField(max_length=60, blank=True)
    evidence = models.TextField(max_length=2000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reason = models.CharField(max_length=500, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=(Q(project__isnull=False, honor__isnull=True) | Q(project__isnull=True, honor__isnull=False)), name='claim_one_record'),
            models.UniqueConstraint(fields=['project', 'applicant'], name='claim_project_applicant'),
            models.UniqueConstraint(fields=['honor', 'applicant'], name='claim_honor_applicant'),
        ]

    @property
    def title(self):
        return self.project.name if self.project_id else self.honor.title


class HonorDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='honor_drafts')
    honor = models.OneToOneField('news.Honor', null=True, blank=True, on_delete=models.SET_NULL, related_name='member_draft')
    draft = models.JSONField(default=dict)
    published = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']

    @property
    def title(self):
        return self.draft.get('title') or '未命名荣誉'


def certificate_path(instance, filename):
    return f'honors/member/{instance.draft_id}/{instance.pk}.jpg'


class Certificate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(HonorDraft, on_delete=models.CASCADE, related_name='images')
    image = models.FileField(upload_to=certificate_path)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    byte_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'证书 {str(self.pk)[:6]} · {self.width} × {self.height}'

    @property
    def public_url(self):
        return reverse('achievements:certificate', args=[self.pk])
