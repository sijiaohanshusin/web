from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client

from projects.tests import make_user
from projects.models import Project, ProjectMember
from news.models import Honor
from achievements.models import Contributor, Claim
from achievements import services


class AchievementContractTests(TestCase):
    def setUp(self):
        self.owner = make_user('author')
        self.member = make_user('member')
        self.officer = make_user('officer', 4)
        self.project = Project.objects.create(name='测试作品', work_year=2026, is_public=True)
        self.person = Contributor.objects.create(project=self.project, name='同名成员', role='硬件')

    def test_name_match_does_not_claim_or_grant_archive_permission(self):
        claim = services.request_claim(self.member, 'work', self.project.pk, self.person.pk, '同名成员', '硬件', '参与原理图设计')
        self.person.refresh_from_db()
        self.assertIsNone(self.person.user_id)
        services.review_claim(self.officer, claim.pk, 'approved', '核验通过')
        self.person.refresh_from_db()
        self.assertEqual(self.person.user_id, self.member.pk)
        self.assertFalse(ProjectMember.objects.filter(project=self.project, user=self.member).exists())

    def test_claimant_cannot_approve_even_if_officer(self):
        claim = services.request_claim(self.officer, 'work', self.project.pk, self.person.pk, '同名成员', '', '证据')
        with self.assertRaises(PermissionDenied):
            services.review_claim(self.officer, claim.pk, 'approved', '自己审核')

    def test_two_same_name_accounts_cannot_take_same_credit(self):
        a = services.request_claim(self.owner, 'work', self.project.pk, self.person.pk, '同名成员', '', '说明 A')
        b = services.request_claim(self.member, 'work', self.project.pk, self.person.pk, '同名成员', '', '说明 B')
        services.review_claim(self.officer, a.pk, 'approved', '核验 A')
        with self.assertRaises(ValidationError):
            services.review_claim(self.officer, b.pk, 'approved', '核验 B')

    def test_private_record_cannot_be_claimed(self):
        self.project.is_public = False
        self.project.save()
        with self.assertRaises(ValidationError):
            services.request_claim(self.member, 'work', self.project.pk, None, '我', '', '说明')

    def test_legacy_honor_can_be_claimed_without_changing_original(self):
        honor = Honor.objects.create(title='历史奖项', year=2024, awardee='旧署名')
        claim = services.request_claim(self.member, 'honor', honor.pk, None, '公开昵称', '获奖成员', '补录说明')
        services.review_claim(self.officer, claim.pk, 'approved', '核验通过')
        honor.refresh_from_db()
        self.assertEqual(honor.awardee, '旧署名')
        self.assertEqual(honor.contributors.get().user_id, self.member.pk)
        self.assertEqual(Honor.summary()['total'], 1)

    def test_duplicate_claim_reuses_pending_request(self):
        for _ in range(2):
            services.request_claim(self.member, 'work', self.project.pk, self.person.pk, '同名成员', '', '说明')
        self.assertEqual(Claim.objects.count(), 1)

    def test_member_cannot_review_or_see_other_claim_evidence(self):
        claim = services.request_claim(self.owner, 'work', self.project.pk, self.person.pk, '同名成员', '', '私密核验材料')
        with self.assertRaises(PermissionDenied):
            services.review_claim(self.member, claim.pk, 'approved', '核验')
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get('/achievements/'), '私密核验材料')
        self.assertEqual(self.client.get('/achievements/review/').status_code, 403)

    def test_account_invitation_requires_own_confirmation(self):
        self.person.invited_user = self.member
        self.person.save()
        with self.assertRaises(PermissionDenied):
            services.respond_invitation(self.owner, self.person.pk, True)
        services.respond_invitation(self.member, self.person.pk, True)
        self.person.refresh_from_db()
        self.assertEqual(self.person.user_id, self.member.pk)

    def test_registered_recruit_can_claim_but_not_create_honor(self):
        recruit = make_user('recruit', 1)
        claim = services.request_claim(recruit, 'work', self.project.pk, None, '新成员', '作者', '旧作品说明')
        services.review_claim(self.officer, claim.pk, 'approved', '核验通过')
        self.client.force_login(recruit)
        self.assertEqual(self.client.post('/achievements/honors/new/').status_code, 403)
        recruit.refresh_from_db()
        self.assertEqual(recruit.member_level, 1)

    def test_anonymous_directory_has_no_member_data(self):
        self.assertEqual(Client().get('/achievements/').status_code, 302)
