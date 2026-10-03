from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from recruitment.models import Campaign
from core.management.commands.update_forum_copy import OLD, NEW


class ForumCopyUpdateTests(TestCase):
    def test_preview_and_idempotent_exact_update_preserve_other_content(self):
        active = Campaign.objects.create(name='Current', intro=f'现行日程\n{OLD}\n联系方式')
        historical = Campaign.objects.create(name='History', intro=OLD, is_active=False)
        custom = Campaign.objects.create(name='Custom', intro='自行编写的说明')
        out = StringIO()
        call_command('update_forum_copy', stdout=out)
        active.refresh_from_db()
        self.assertIn(OLD, active.intro)
        self.assertIn(f'Would update campaign {active.pk}', out.getvalue())
        for _ in range(2):
            call_command('update_forum_copy', apply=True, stdout=StringIO())
        active.refresh_from_db(); historical.refresh_from_db(); custom.refresh_from_db()
        self.assertEqual(active.intro, f'现行日程\n{NEW}\n联系方式')
        self.assertEqual(historical.intro, OLD)
        self.assertEqual(custom.intro, '自行编写的说明')
