from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import roles

from .models import PointLog
from .services import award_points, total_for

User = get_user_model()


class PointServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="p1", password="x", is_active=True)

    def test_award_and_total(self):
        award_points(self.user, 5, source=PointLog.Source.EVENT_CHECKIN, note="签到")
        award_points(self.user, -2, source=PointLog.Source.ADMIN_ADJUST, note="扣分")
        self.assertEqual(total_for(self.user), 3)

    def test_zero_delta_skipped(self):
        self.assertIsNone(award_points(self.user, 0, source=PointLog.Source.ADMIN_ADJUST))
        self.assertEqual(self.user.point_logs.count(), 0)


class PointViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="p1", password="Str0ngPass!2025", is_active=True)

    def test_mine_requires_login(self):
        resp = self.client.get(reverse("points:mine"))
        self.assertEqual(resp.status_code, 302)

    def test_mine_shows_logs(self):
        award_points(self.user, 5, source=PointLog.Source.EVENT_CHECKIN, note="活动签到：C 语言培训")
        self.client.login(username="p1", password="Str0ngPass!2025")
        resp = self.client.get(reverse("points:mine"))
        self.assertContains(resp, "C 语言培训")
        self.assertContains(resp, "+5")

    def test_leaderboard_public_and_ordered(self):
        u2 = User.objects.create_user(username="p2", password="x", is_active=True, real_name="第二名")
        award_points(self.user, 3, source=PointLog.Source.ADMIN_ADJUST)
        award_points(u2, 10, source=PointLog.Source.ADMIN_ADJUST)
        resp = self.client.get(reverse("points:leaderboard"))
        rows = resp.context["rows"]
        self.assertEqual(rows[0].pk, u2.pk)
        self.assertEqual(rows[0].total, 10)

    def test_bulk_adjust_from_members_page(self):
        officer = User.objects.create_user(username="off", password="Str0ngPass!2025", is_active=True)
        officer.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="off", password="Str0ngPass!2025")
        resp = self.client.post(reverse("dashboard:member_action"), {
            "action": "points_adjust", "ids": [self.user.pk],
            "points_delta": "8", "points_note": "电赛校赛一等奖",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(total_for(self.user), 8)
        log = self.user.point_logs.get()
        self.assertEqual(log.operator, officer)
        self.assertEqual(self.user.notifications.count(), 1)
