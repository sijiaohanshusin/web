import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .schema import empty_design


def eligible(user):
    return bool(user.is_authenticated and user.is_active and (user.member_level >= 3 or user.is_superuser))


class ShowcaseQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(user__is_active=True, blocked=False, published__isnull=False).filter(
            Q(user__member_level__gte=3) | Q(user__is_superuser=True)
        )


class Showcase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="showcase")
    draft = models.JSONField(default=empty_design)
    published = models.JSONField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    public_name = models.CharField(max_length=30, blank=True, db_index=True)
    public_tags = models.CharField(max_length=60, blank=True)
    public_cohort = models.CharField(max_length=4, blank=True, db_index=True)
    public_direction = models.CharField(max_length=12, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    blocked = models.BooleanField(default=False)
    moderation_reason = models.CharField(max_length=500, blank=True)
    withdrawal_reason = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ShowcaseQuerySet.as_manager()

    class Meta:
        verbose_name = "成员展示"
        verbose_name_plural = "成员展示"

    def __str__(self):
        return self.public_name or "未发布的成员展示"


class ShowcaseAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    showcase = models.ForeignKey(Showcase, on_delete=models.CASCADE, related_name="assets")
    image = models.FileField(upload_to="showcase/")
    thumbnail = models.FileField(upload_to="showcase/")
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    display_name = models.CharField(max_length=120, blank=True)
    byte_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class ModerationEvent(models.Model):
    showcase = models.ForeignKey(Showcase, on_delete=models.CASCADE, related_name="moderation_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=12)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
