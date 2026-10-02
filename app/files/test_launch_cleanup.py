import tempfile
from io import StringIO
from pathlib import Path
from django.core.management import call_command, CommandError
from django.test import TestCase
from files.models import Resource


class LaunchCleanupTests(TestCase):
    def setUp(self):
        Resource.objects.bulk_create([
            Resource(title='test1', size=56, file='audit/test1.txt'),
            Resource(title='test', size=1817, file='audit/test.txt'),
            Resource(title='real lesson', size=1817, file='audit/real.txt'),
        ])

    def test_preview_is_read_only_and_apply_retains_other_files(self):
        call_command('restrict_launch_test_files', stdout=StringIO())
        self.assertEqual(Resource.objects.filter(min_level=0).count(), 3)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'before.json'
            call_command('restrict_launch_test_files', apply=True, snapshot=path, stdout=StringIO())
            self.assertTrue(path.exists())
        self.assertEqual(Resource.objects.filter(min_level=4).count(), 2)
        self.assertEqual(Resource.objects.get(title='real lesson').min_level, 0)
        self.assertEqual(Resource.objects.count(), 3)

    def test_ambiguous_match_stops_before_any_change(self):
        Resource.objects.bulk_create([Resource(title='test', size=1817, file='audit/other.txt')])
        with self.assertRaises(CommandError):
            call_command('restrict_launch_test_files', apply=True, stdout=StringIO())
        self.assertFalse(Resource.objects.filter(min_level=4).exists())
