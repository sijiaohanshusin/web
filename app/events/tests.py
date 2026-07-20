from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import roles
from points.services import total_for

from .models import Event, EventSignup

User = get_user_model()


def make_event(**kw):
    now = timezone.now()
    defaults = {
        "title": "STM32 入门培训",
        "kind": Event.Kind.TRAINING,
        "description": "带电脑，装好 **Keil**。",
        "location": "21B 实验室",
        "start_at": now + timedelta(days=1),
        "end_at": now + timedelta(days=1, hours=2),
        "points_reward": 5,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_user(name="stu", level=roles.LEVEL_FORMAL):
    u = User.objects.create_user(username=name, password="Str0ngPass!2025", is_active=True)
    u.set_level(level)
    return u


class EventListTests(TestCase):
    def test_upcoming_and_past_tabs(self):
        make_event(title="未来培训")
        make_event(
            title="过去培训",
            start_at=timezone.now() - timedelta(days=2),
            end_at=timezone.now() - timedelta(days=2, hours=-2),
        )
        resp = self.client.get(reverse("events:list"))
        self.assertContains(resp, "未来培训")
        self.assertNotContains(resp, "过去培训")
        resp = self.client.get(reverse("events:list"), {"tab": "past"})
        self.assertContains(resp, "过去培训")

    def test_level_gated_hidden(self):
        make_event(title="干事内训", min_level=Event.MinLevel.OFFICER)
        resp = self.client.get(reverse("events:list"))
        self.assertNotContains(resp, "干事内训")

    def test_unpublished_hidden(self):
        make_event(title="草稿活动", is_published=False)
        resp = self.client.get(reverse("events:list"))
        self.assertNotContains(resp, "草稿活动")


class EventSignupTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def test_signup_and_cancel(self):
        resp = self.client.post(reverse("events:signup", args=[self.event.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EventSignup.objects.filter(event=self.event, user=self.user).exists())
        self.assertEqual(self.user.notifications.filter(kind="event").count(), 1)

        self.client.post(reverse("events:cancel", args=[self.event.pk]))
        self.assertFalse(EventSignup.objects.filter(event=self.event, user=self.user).exists())

    def test_signup_twice_is_noop(self):
        self.client.post(reverse("events:signup", args=[self.event.pk]))
        self.client.post(reverse("events:signup", args=[self.event.pk]))
        self.assertEqual(EventSignup.objects.filter(event=self.event).count(), 1)

    def test_capacity_full(self):
        self.event.capacity = 1
        self.event.save()
        other = make_user("other")
        EventSignup.objects.create(event=self.event, user=other)
        resp = self.client.post(reverse("events:signup", args=[self.event.pk]), follow=True)
        self.assertContains(resp, "名额已满")
        self.assertFalse(EventSignup.objects.filter(event=self.event, user=self.user).exists())

    def test_deadline_passed(self):
        self.event.signup_deadline = timezone.now() - timedelta(hours=1)
        self.event.save()
        resp = self.client.post(reverse("events:signup", args=[self.event.pk]), follow=True)
        self.assertContains(resp, "报名已截止")

    def test_level_gate(self):
        self.event.min_level = Event.MinLevel.OFFICER
        self.event.save()
        resp = self.client.post(reverse("events:signup", args=[self.event.pk]), follow=True)
        self.assertFalse(EventSignup.objects.filter(event=self.event, user=self.user).exists())


class EventCheckinTests(TestCase):
    def setUp(self):
        self.event = make_event(start_at=timezone.now() - timedelta(minutes=10),
                                end_at=timezone.now() + timedelta(hours=2))
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def test_checkin_flow_awards_points(self):
        EventSignup.objects.create(event=self.event, user=self.user)
        code = self.event.open_checkin()

        resp = self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": code.lower()})
        self.assertEqual(resp.status_code, 302)
        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertTrue(signup.checked_in)
        self.assertFalse(signup.is_walkin)
        self.assertEqual(total_for(self.user), 5)

    def test_walkin_checkin_creates_signup(self):
        code = self.event.open_checkin()
        self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": code})
        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertTrue(signup.is_walkin)
        self.assertTrue(signup.checked_in)

    def test_wrong_code_rejected(self):
        self.event.open_checkin()
        self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": "XXXXXX"})
        self.assertFalse(EventSignup.objects.filter(event=self.event, user=self.user, checkin_at__isnull=False).exists())
        self.assertEqual(total_for(self.user), 0)

    def test_checkin_closed_rejected(self):
        self.event.open_checkin()
        self.event.close_checkin()
        self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": self.event.checkin_code})
        self.assertEqual(total_for(self.user), 0)

    def test_double_checkin_no_double_points(self):
        code = self.event.open_checkin()
        self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": code})
        self.client.post(reverse("events:checkin", args=[self.event.pk]), {"code": code})
        self.assertEqual(total_for(self.user), 5)


class EventDashboardTests(TestCase):
    def setUp(self):
        self.officer = make_user("off", roles.LEVEL_OFFICER)
        self.client.login(username="off", password="Str0ngPass!2025")

    def test_member_cannot_access(self):
        make_user("m")
        self.client.login(username="m", password="Str0ngPass!2025")
        resp = self.client.get(reverse("dashboard:events"))
        self.assertEqual(resp.status_code, 403)

    def test_create_event(self):
        start = timezone.now() + timedelta(days=3)
        resp = self.client.post(reverse("dashboard:event_create"), {
            "title": "暑期电赛宣讲",
            "kind": "contest",
            "location": "启航剧场",
            "start_at": start.strftime("%Y-%m-%dT%H:%M"),
            "end_at": (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            "signup_deadline": "",
            "capacity": 100,
            "min_level": 0,
            "points_reward": 5,
            "is_published": "on",
            "description": "## 议程\n\n电赛介绍与组队",
        })
        self.assertEqual(resp.status_code, 302)
        e = Event.objects.get(title="暑期电赛宣讲")
        self.assertEqual(e.created_by, self.officer)

    def test_form_rejects_bad_times(self):
        start = timezone.now() + timedelta(days=3)
        resp = self.client.post(reverse("dashboard:event_create"), {
            "title": "时间错乱活动", "kind": "other", "location": "",
            "start_at": start.strftime("%Y-%m-%dT%H:%M"),
            "end_at": (start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "signup_deadline": "", "capacity": 0, "min_level": 0,
            "points_reward": 0, "description": "x",
        })
        self.assertContains(resp, "结束时间必须晚于开始时间")

    def test_open_checkin_and_signups_page(self):
        event = make_event(created_by=self.officer)
        member = make_user("m2")
        EventSignup.objects.create(event=event, user=member)

        self.client.post(reverse("dashboard:events"), {"id": event.pk, "action": "open_checkin"})
        event.refresh_from_db()
        self.assertTrue(event.checkin_open)
        self.assertEqual(len(event.checkin_code), 6)

        resp = self.client.get(reverse("dashboard:event_signups", args=[event.pk]))
        self.assertContains(resp, event.checkin_code)
        self.assertContains(resp, "m2")

    def test_csv_export(self):
        event = make_event(created_by=self.officer)
        member = make_user("m3")
        EventSignup.objects.create(event=event, user=member)
        resp = self.client.get(reverse("dashboard:event_signups", args=[event.pk]), {"export": "csv"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn("m3", resp.content.decode("utf-8-sig"))

    def test_manual_checkin_awards_points(self):
        event = make_event(created_by=self.officer)
        member = make_user("m4")
        signup = EventSignup.objects.create(event=event, user=member)
        self.client.post(reverse("dashboard:event_signups", args=[event.pk]), {
            "action": "manual_checkin", "signup_id": signup.pk,
        })
        signup.refresh_from_db()
        self.assertTrue(signup.checked_in)
        self.assertEqual(total_for(member), 5)

    def test_qr_endpoint(self):
        event = make_event(created_by=self.officer)
        event.open_checkin()
        resp = self.client.get(reverse("dashboard:event_qr", args=[event.pk]))
        self.assertEqual(resp["Content-Type"], "image/png")


class ReminderCommandTests(TestCase):
    def test_reminder_sent_once(self):
        event = make_event(start_at=timezone.now() + timedelta(hours=3),
                           end_at=timezone.now() + timedelta(hours=5))
        far_event = make_event(title="下周活动",
                               start_at=timezone.now() + timedelta(days=6),
                               end_at=timezone.now() + timedelta(days=6, hours=2))
        user = make_user()
        EventSignup.objects.create(event=event, user=user)
        EventSignup.objects.create(event=far_event, user=user)

        call_command("send_event_reminders")
        self.assertEqual(user.notifications.filter(title__contains="即将开始").count(), 1)

        call_command("send_event_reminders")
        self.assertEqual(user.notifications.filter(title__contains="即将开始").count(), 1)
