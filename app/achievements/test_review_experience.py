from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase

from news.models import Honor
from projects.tests import make_user
from . import services
from .models import Claim, Contributor


class ReviewExperienceTests(TestCase):
    def setUp(self):
        self.officer = make_user('claim-review-officer', 4)
        self.other = make_user('claim-review-other', 4)
        self.honor = Honor.objects.create(title='核验演示奖项', year=2026, level=30)
        self.claim = services.request_claim(self.officer, 'honor', self.honor.pk,
                                            None, '公开署名', '软件', '参与事实说明')
        self.url = '/achievements/review/'
        self.client.force_login(self.officer)

    def test_own_pending_claim_explains_why_review_is_unavailable(self):
        response = self.client.get(self.url)
        self.assertContains(response, '这是你本人提交的认领申请')
        self.assertContains(response, '请另一位站务人员核验')
        self.assertNotContains(response, 'name="decision"')
        self.assertNotContains(response, 'name="reason"')

    def test_stale_form_self_review_returns_explanation_without_mutation(self):
        for decision in ('approved', 'rejected'):
            with self.subTest(decision=decision):
                response = self.client.post(self.url, {
                    'claim': self.claim.pk, 'decision': decision, 'reason': '核验说明',
                }, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '请另一位站务人员核验')
                self.claim.refresh_from_db()
                self.assertEqual(self.claim.status, Claim.Status.PENDING)
                self.assertIsNone(self.claim.reviewer_id)
                self.assertFalse(Contributor.objects.exists())

    def test_system_administrator_cannot_self_review_either(self):
        self.officer.is_superuser = True
        self.officer.save()
        response = self.client.post(self.url, {
            'claim': self.claim.pk, 'decision': 'approved', 'reason': '核验说明',
        }, follow=True)
        self.assertContains(response, '请另一位站务人员核验')
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.PENDING)

    def test_service_still_rejects_self_review(self):
        with self.assertRaises(PermissionDenied):
            services.review_claim(self.officer, self.claim.pk, 'approved', '核验说明')
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.PENDING)

    def test_another_officer_can_review_the_same_claim(self):
        self.client.force_login(self.other)
        self.assertContains(self.client.get(self.url), 'name="decision"')
        response = self.client.post(self.url, {
            'claim': self.claim.pk, 'decision': 'approved', 'reason': '核对事实通过',
        })
        self.assertRedirects(response, self.url)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.APPROVED)
        self.assertEqual(self.claim.reviewer_id, self.other.pk)
        self.assertEqual(self.claim.contributor.user_id, self.officer.pk)

    def test_non_officer_is_still_forbidden(self):
        self.client.force_login(make_user('claim-review-member', 3))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {
            'claim': self.claim.pk, 'decision': 'approved', 'reason': '核验说明',
        }).status_code, 403)

    def test_review_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.other)
        self.assertEqual(client.post(self.url, {
            'claim': self.claim.pk, 'decision': 'approved', 'reason': '核验说明',
        }).status_code, 403)
