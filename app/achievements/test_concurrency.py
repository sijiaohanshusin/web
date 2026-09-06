from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from projects.tests import make_user
from projects.models import Project
from projects import work_services
from .models import Contributor
from .services import request_claim, review_claim


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL row locks')
class LedgerConcurrencyTests(TransactionTestCase):
    def test_two_people_cannot_claim_one_credit_concurrently(self):
        a, b, officer = make_user('claim-a'), make_user('claim-b'), make_user('claim-staff', 4)
        project = Project.objects.create(name='并发认领', is_public=True)
        person = Contributor.objects.create(project=project, name='同名')
        claims = [request_claim(u, 'work', project.pk, person.pk, '同名', '', '核验说明') for u in (a, b)]
        barrier = Barrier(2)

        def run(claim):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                review_claim(officer, claim.pk, 'approved', '已核验')
                return 'linked'
            except ValidationError:
                return 'conflict'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(run, claims)), ['linked', 'conflict'])

    def test_duplicate_publication_is_serialized(self):
        authors = [make_user('publish-a'), make_user('publish-b')]
        data = dict(name='同一件作品', year=2026, credit='同一团队', department='hardware', summary='', highlight='', tags='', external_url='', cover='', gallery=[])
        works = [work_services.save_work(u, (w := work_services.create_work(u)).pk, w.version, data) for u in authors]
        barrier = Barrier(2)

        def run(pair):
            user, work = pair
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                work_services.publish_work(user, work.pk, work_services.preview_token(work), 'on')
                return 'published'
            except ValidationError:
                return 'duplicate'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(run, zip(authors, works))), ['published', 'duplicate'])
        self.assertEqual(Project.public().count(), 1)
