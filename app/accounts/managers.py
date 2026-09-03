from django.contrib.auth.models import UserManager
from django.db import models, transaction


class MemberQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if not {"is_active", "member_level", "is_superuser"}.intersection(kwargs):
            return super().update(**kwargs)
        from showcase.services import revoke_ineligible
        with transaction.atomic(using=self.db):
            ids = list(self.select_for_update().values_list("pk", flat=True))
            count = super().update(**kwargs)
            revoke_ineligible(self.model.objects.using(self.db).filter(pk__in=ids), self.db)
            return count


class MemberManager(UserManager.from_queryset(MemberQuerySet)):
    pass
