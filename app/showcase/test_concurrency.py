from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from accounts.models import User
from .services import Conflict, change, get_showcase, preview_ticket


@skipUnless(connection.vendor == "postgresql", "Row-lock races require PostgreSQL; exercised in release rehearsal")
class PostgresConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="concurrent-member", member_level=3)
        self.sc = get_showcase(self.user)
        self.data = self.sc.draft
        self.data["nickname"] = "并发测试成员"

    def test_exactly_one_same_revision_save_wins(self):
        barrier = Barrier(2)

        def save(index):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                change(user, "save", 0, {**self.data, "nickname": f"版本{index}"})
                return "saved"
            except Conflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (1, 2)))
        self.assertCountEqual(results, ["saved", "conflict"])
        self.sc.refresh_from_db()
        self.assertEqual(self.sc.revision, 1)

    def test_deactivation_racing_publication_always_ends_hidden(self):
        barrier = Barrier(2)
        ticket = preview_ticket(self.sc, self.data)

        def execute(action):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                if action == "publish":
                    try:
                        change(user, "publish", 0, self.data, True, ticket)
                    except (PermissionDenied, Conflict):
                        pass
                else:
                    User.objects.filter(pk=user.pk).update(is_active=False)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(execute, ("publish", "deactivate")))
        self.sc.refresh_from_db()
        self.assertIsNone(self.sc.published)
