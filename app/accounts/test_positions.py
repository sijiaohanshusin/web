from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts import roles
from accounts.models import Position, PositionAppointment, User
from accounts.sso import SsoCookieMiddleware


class PositionTermTests(TestCase):
    def setUp(self):
        self.chair = Position.objects.get(name="主席")
        self.user = User.objects.create_user(username="term_member", member_level=roles.LEVEL_FORMAL, grade="2024")

    def appoint(self, term=2025):
        self.user.position = self.chair
        self.user.position_term_start = term
        self.user.save(update_fields=["position", "position_term_start"])

    def test_term_is_separate_from_enrolment_and_does_not_publish(self):
        self.appoint()
        self.user.refresh_from_db()
        self.assertEqual(self.user.grade, "2024")
        self.assertEqual(self.user.position_term_label, "2025-2026 届")
        self.assertFalse(self.user.show_on_team)
        record = self.user.position_appointments.get()
        self.assertEqual(record.term_start, 2025)
        self.assertIsNone(record.ended_at)

    def test_repeated_saves_do_not_duplicate_history(self):
        self.appoint()
        self.appoint()
        self.user.real_name = "改名"
        self.user.save()
        self.assertEqual(self.user.position_appointments.count(), 1)

    def test_next_term_archives_previous_tenure(self):
        self.appoint(2024)
        old = self.user.position_appointments.get()
        self.appoint(2025)
        old.refresh_from_db()
        self.assertIsNotNone(old.ended_at)
        self.assertEqual(old.term_start, 2024)
        self.assertEqual(self.user.position_appointments.filter(ended_at=None).count(), 1)

    def test_filling_an_unknown_term_corrects_the_current_record(self):
        self.appoint(None)
        old_id = self.user.position_appointments.get().pk
        self.appoint(2025)
        self.assertEqual(self.user.position_appointments.get().pk, old_id)
        self.assertEqual(self.user.position_appointments.get().term_start, 2025)

    def test_unassign_removes_only_position_permissions_and_sso_group(self):
        self.appoint()
        self.assertTrue(roles.is_officer(self.user))
        self.assertIn("主席", SsoCookieMiddleware._forum_groups(self.user))
        self.user.position = None
        self.user.save(update_fields=["position"])
        self.user.refresh_from_db()
        self.assertFalse(roles.is_officer(self.user))
        self.assertNotIn("主席", SsoCookieMiddleware._forum_groups(self.user))
        self.assertEqual(self.user.member_level, roles.LEVEL_FORMAL)
        self.assertIsNone(self.user.position_term_start)
        self.assertIsNotNone(self.user.position_appointments.get().ended_at)

    def test_explicit_staff_and_level_survive_unassignment(self):
        self.user.member_level = roles.LEVEL_OFFICER
        self.user.is_staff = True
        self.user.save()
        self.appoint()
        self.user.position = None
        self.user.save(update_fields=["position"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertTrue(roles.is_officer(self.user))
        self.assertEqual(self.user.member_level, roles.LEVEL_OFFICER)

    def test_deleting_custom_position_keeps_its_history(self):
        self.chair = Position.objects.create(name="历任技术部长")
        self.appoint()
        self.chair.delete()
        self.user.refresh_from_db()
        self.assertIsNone(self.user.position)
        self.assertIsNone(self.user.position_term_start)
        record = self.user.position_appointments.get()
        self.assertIsNone(record.position)
        self.assertEqual(record.position_name, "历任技术部长")
        self.assertIsNotNone(record.ended_at)

    def test_history_tracks_only_fields_actually_saved(self):
        self.appoint(2025)
        self.user.position_term_start = 2024
        self.user.save(update_fields=["position"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.position_term_start, 2025)
        self.assertEqual(self.user.position_appointments.count(), 1)


class PositionHistoryViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="history_admin", is_staff=True)
        self.client.force_login(self.admin)
        self.member = User.objects.create_user(username="former_chair", real_name="历任测试成员", member_level=3)
        self.chair = Position.objects.get(name="主席")

    def post(self, **overrides):
        data = {"form": "assign", "user_id": self.member.username, "position_id": self.chair.pk,
                "term_start": "2025", "appointment_status": "history"}
        data.update(overrides)
        return self.client.post(reverse("dashboard:positions"), data, follow=True)

    def test_history_only_is_idempotent_and_never_grants_permissions(self):
        self.post()
        self.post()
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)
        self.assertFalse(self.member.is_officer)
        self.assertEqual(self.member.member_level, 3)
        self.assertFalse(self.member.show_on_team)
        self.assertEqual(self.member.position_appointments.count(), 1)
        record = self.member.position_appointments.get()
        self.assertIsNotNone(record.ended_at)
        self.assertEqual(record.operator, self.admin)

    def test_history_only_does_not_replace_a_current_position(self):
        self.member.position = Position.objects.get(name="软件副主席")
        self.member.position_term_start = 2026
        self.member.save()
        current = self.member.position
        self.post()
        self.member.refresh_from_db()
        self.assertEqual(self.member.position, current)
        self.assertEqual(self.member.position_term_start, 2026)

    def test_current_assignment_sets_term_and_unassignment_keeps_it_in_history(self):
        self.post(appointment_status="current")
        self.member.refresh_from_db()
        self.assertEqual(self.member.position_term_start, 2025)
        self.assertEqual(self.member.position, self.chair)
        self.client.post(reverse("dashboard:positions"), {"form": "unassign", "user_id": self.member.pk})
        self.assertEqual(self.member.position_appointments.get().term_start, 2025)
        self.assertIsNotNone(self.member.position_appointments.get().ended_at)

    def test_invalid_or_missing_historical_term_does_not_mutate(self):
        for term in ("", "wrong", "²", "1800", "9999"):
            with self.subTest(term=term):
                response = self.post(term_start=term)
                self.assertContains(response, "请选择有效的任职届次")
        self.assertFalse(PositionAppointment.objects.filter(user=self.member).exists())

    def test_history_can_be_filtered_by_term_and_member(self):
        self.post(term_start="2024")
        self.post(term_start="2025")
        response = self.client.get(reverse("dashboard:positions"), {"history_q": "former_", "history_term": "2024"})
        self.assertEqual([record.term_start for record in response.context["history"]], [2024])

    def test_historical_roles_are_private_and_visible_to_the_member(self):
        self.post()
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("accounts:profile")), "2025-2026 届")
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("team:wall")), "历任测试成员")


class PositionMigrationTests(TransactionTestCase):
    def test_existing_assignments_are_preserved_without_inventing_terms(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0007_applicant_profile_fields")])
        old_apps = executor.loader.project_state([("accounts", "0007_applicant_profile_fields")]).apps
        OldUser = old_apps.get_model("accounts", "User")
        OldPosition = old_apps.get_model("accounts", "Position")
        chair = OldPosition.objects.create(name="迁移测试主席")
        user = OldUser.objects.create(username="legacy_chair", position=chair, member_level=5, is_staff=True, is_active=True)
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("accounts", "0009_backfill_position_appointments")])
            current = User.objects.get(pk=user.pk)
            self.assertEqual(current.position_id, chair.pk)
            self.assertEqual(current.member_level, 5)
            self.assertTrue(current.is_staff)
            self.assertTrue(current.is_active)
            self.assertIsNone(current.position_term_start)
            record = current.position_appointments.get()
            self.assertIsNone(record.term_start)
            self.assertIsNone(record.started_at)
            self.assertIsNone(record.ended_at)
        finally:
            MigrationExecutor(connection).migrate([("accounts", "0009_backfill_position_appointments")])
