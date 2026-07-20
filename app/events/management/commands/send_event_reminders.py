"""活动开场提醒：给 24 小时内开始且未提醒过的报名成员发站内通知。

由 systemd timer（heuesta-event-reminder.timer）每小时执行一次，也可手动跑：
    python manage.py send_event_reminders
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import EventSignup
from notify.models import Notification
from notify.services import notify_user


class Command(BaseCommand):
    help = "给 24 小时内开场的活动报名者发站内提醒（幂等）"

    def handle(self, *args, **options):
        now = timezone.now()
        window_end = now + timedelta(hours=24)
        pending = (
            EventSignup.objects.filter(
                reminded=False,
                event__is_published=True,
                event__start_at__gt=now,
                event__start_at__lte=window_end,
            )
            .select_related("event", "user")
        )

        sent = 0
        for signup in pending:
            event = signup.event
            notify_user(
                signup.user, f"活动即将开始：{event.title}",
                kind=Notification.Kind.EVENT,
                body=f"{event.start_at:%m 月 %d 日 %H:%M} · {event.location or '地点见详情'}，记得现场签到",
                url=event.get_absolute_url(),
            )
            signup.reminded = True
            signup.save(update_fields=["reminded"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"sent {sent} reminder(s)"))
