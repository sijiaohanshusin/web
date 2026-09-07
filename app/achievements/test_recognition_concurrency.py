import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.db import connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from projects.tests import make_user, make_cover
from . import recognition, honor_services
from .models import Certificate, RecognitionGate, RecognitionTask


@skipUnless(connection.vendor == 'postgresql', 'Requires an isolated PostgreSQL database')
class RecognitionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        config = override_settings(MEDIA_ROOT=media.name, HONOR_AI_ENABLED=True,
            DASHSCOPE_API_KEY='concurrency-test-not-a-key', DASHSCOPE_WORKSPACE_ID='local-test',
            HONOR_AI_FREE_TIER_CONFIRMED=True,
            HONOR_AI_FREE_TIER_EXPIRES=(timezone.now()+timedelta(days=2)).isoformat())
        config.enable(); self.addCleanup(config.disable)
        RecognitionGate.objects.get_or_create(pk=1)
        self.user = make_user('recognition-race')
        self.draft = honor_services.create(self.user)
        self.image, self.version = recognition.upload_certificate(self.user, self.draft.pk, 0, make_cover())

    def test_duplicate_start_only_reserves_one_call(self):
        barrier = Barrier(2)
        def start(_):
            try:
                image = Certificate.objects.get(pk=self.image.pk)
                barrier.wait(timeout=10)
                return recognition.start(image, 'on').pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(start, (1, 2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(RecognitionTask.objects.count(), 1)
        self.assertEqual(RecognitionGate.objects.get(pk=1).counters['total'], 1)

    def test_deleting_running_task_cannot_bypass_worker_lease(self):
        second, _ = recognition.upload_certificate(self.user, self.draft.pk, self.version, make_cover())
        recognition.start(self.image, 'on')
        recognition.start(second, 'on')
        entered, release = Event(), Event()
        def provider(_):
            entered.set()
            if not release.wait(timeout=10):
                raise AssertionError('Worker was not released')
            return {'title': 'Local test'}, {}
        def worker():
            try:
                return recognition.process_one()
            finally:
                connections.close_all()
        with patch.object(recognition, 'call_model', side_effect=provider) as call:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(worker)
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    self.image.delete()
                    self.assertFalse(recognition.process_one())
                    call.assert_called_once()
                finally:
                    release.set()
                self.assertTrue(future.result(timeout=10))
        self.assertIsNone(RecognitionGate.objects.get(pk=1).lease)
        with patch.object(recognition, 'call_model', return_value=({}, {})):
            self.assertTrue(recognition.process_one())
        self.assertEqual(RecognitionTask.objects.count(), 1)
