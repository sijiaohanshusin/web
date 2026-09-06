from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from accounts.models import User
from .models import Project
from .work_services import WorkConflict, create_work, preview_token, publish_work, save_work


@skipUnless(connection.vendor == 'postgresql', 'Row-lock races require isolated PostgreSQL CI')
class WorkConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='concurrent-author', member_level=3)
        self.work = create_work(self.user)
        self.data = dict(name='并发作品', year=2026, credit='演示署名', summary='', highlight='',
                         department='hardware', tags='', external_url='', cover='', gallery=[])

    def test_same_version_has_one_successful_save(self):
        barrier = Barrier(2)

        def write(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                save_work(self.user, self.work.pk, 0, {**self.data, 'name': f'版本{index}'})
                return 'saved'
            except WorkConflict:
                return 'conflict'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(write, (1, 2))), ['saved', 'conflict'])

    def test_deactivate_racing_publish_stays_withdrawn(self):
        work = save_work(self.user, self.work.pk, 0, self.data)
        ticket = preview_token(work)
        barrier = Barrier(2)

        def write(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if action == 'publish':
                    try:
                        publish_work(self.user, work.pk, ticket, 'on')
                    except (PermissionDenied, WorkConflict):
                        pass
                else:
                    User.objects.filter(pk=self.user.pk).update(is_active=False)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(write, ('publish', 'deactivate')))
        work.refresh_from_db()
        self.assertIsNone(work.published)
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        self.assertFalse(Project.public().exists())
