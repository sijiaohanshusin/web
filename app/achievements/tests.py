from copy import deepcopy
import tempfile

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse

from news.models import Honor, Post
from projects.models import MemberWork, Project
from projects.tests import make_user, make_cover
from projects import work_services
from . import services, honor_services
from .forms import HonorForm, people_set, people_data
from .models import HonorDraft, Contributor, Claim


class HonorPublicationTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.owner, self.other, self.officer = make_user('owner'), make_user('other'), make_user('staff', 4)
        self.client.force_login(self.owner)
        self.draft = honor_services.create(self.owner)

    def save(self, upload=None, **changes):
        data = {'title': '系统设计竞赛一等奖', 'contest': '系统设计竞赛', 'level': 30, 'year': 2026,
                'awardee': '演示一队', 'note': '虚构测试记录', 'project': None, 'certificate': '', 'contributors': []}
        data.update(self.draft.draft)
        data.update(changes)
        self.draft = honor_services.save(self.owner, self.draft.pk, self.draft.version, data, upload)

    def publish(self):
        self.draft = honor_services.publish(self.owner, self.draft.pk, honor_services.token(self.draft), 'on')

    def test_draft_publication_update_withdraw(self):
        self.save()
        visitor = Client()
        self.assertNotContains(visitor.get('/honors/'), '系统设计竞赛一等奖')
        self.publish()
        self.assertContains(visitor.get('/honors/'), '系统设计竞赛一等奖')
        self.save(title='新的公开标题')
        self.assertNotContains(visitor.get('/honors/'), '新的公开标题')
        self.publish()
        self.assertContains(visitor.get('/honors/'), '新的公开标题')
        honor_services.withdraw(self.owner, self.draft.pk, self.draft.version)
        self.assertNotContains(visitor.get('/honors/'), '新的公开标题')
        self.assertEqual(Honor.summary()['total'], 0)

    @override_settings(DEBUG=True)
    def test_certificate_private_draft_live_and_revoked(self):
        self.save(upload=make_cover())
        image = self.draft.images.get()
        visitor = Client()
        self.assertEqual(visitor.get(image.public_url).status_code, 404)
        self.assertEqual(visitor.get('/media/' + image.image.name).status_code, 403)
        own_response = self.client.get(image.public_url)
        self.assertEqual(own_response.status_code, 200)
        own_response.close()
        self.publish()
        response = visitor.get(image.public_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        response.close()
        self.assertContains(visitor.get('/honors/'), image.public_url)
        self.assertNotContains(visitor.get('/honors/'), '/media/honors/member/')
        honor_services.withdraw(self.owner, self.draft.pk, self.draft.version)
        self.assertEqual(visitor.get(image.public_url).status_code, 404)

    def test_certificate_cannot_borrow_other_draft_image(self):
        other = honor_services.create(self.other)
        self.save(upload=make_cover())
        form = HonorForm(other, {**self.draft.draft, 'version': 0})
        self.assertFalse(form.is_valid())
        self.assertIn('certificate', form.errors)

    def test_certificate_in_use_cannot_delete(self):
        self.save(upload=make_cover())
        image = self.draft.images.get()
        self.publish()
        self.save(certificate='')
        with self.assertRaises(ValidationError):
            honor_services.remove_image(self.owner, self.draft.pk, self.draft.version, image.pk)
        self.publish()
        honor_services.remove_image(self.owner, self.draft.pk, self.draft.version, image.pk)
        self.assertFalse(self.draft.images.exists())

    def test_version_conflict_and_stale_preview(self):
        self.save()
        token = honor_services.token(self.draft)
        version = self.draft.version
        self.save(note='另一标签页更新')
        with self.assertRaises(work_services.WorkConflict):
            honor_services.save(self.owner, self.draft.pk, version, self.draft.draft)
        with self.assertRaises(work_services.WorkConflict):
            honor_services.publish(self.owner, self.draft.pk, token, 'on')
        self.assertFalse(Honor.objects.exists())

    def test_publish_requires_explicit_consent(self):
        self.save()
        with self.assertRaises(ValidationError):
            honor_services.publish(self.owner, self.draft.pk, honor_services.token(self.draft), None)

    def test_member_ownership_is_enforced_for_all_writes(self):
        self.save()
        self.client.force_login(self.other)
        for action in ('honor_edit', 'honor_preview', 'honor_publish', 'honor_withdraw', 'honor_delete'):
            url = reverse('achievements:' + action, args=[self.draft.pk])
            response = self.client.get(url) if action in ('honor_edit', 'honor_preview') else self.client.post(url)
            self.assertEqual(response.status_code, 404, action)

    def test_officers_rank_without_republishing_or_legacy_edit(self):
        self.save()
        self.publish()
        self.client.force_login(self.officer)
        h = self.draft.honor
        response = self.client.post('/achievements/honors/manage/', {'honor': h.pk, 'importance': 90, 'is_featured': 'on', 'title': '不得改名'})
        self.assertEqual(response.status_code, 302)
        h.refresh_from_db()
        self.assertEqual(h.importance, 90)
        self.assertEqual(h.title, self.draft.draft['title'])
        for action in ('delete', 'toggle_public', 'toggle_featured', 'save'):
            self.assertEqual(self.client.post('/dashboard/honors/', {'id': h.pk, 'action': action}).status_code, 404)
        self.assertEqual(self.client.get(f'/dashboard/honors/?edit={h.pk}').status_code, 404)
        request = RequestFactory().get('/admin/news/honor/')
        request.user = self.officer
        self.assertFalse(admin.site._registry[Honor].get_queryset(request).filter(pk=h.pk).exists())

    def test_exact_duplicate_not_counted_twice_but_distinct_team_allowed(self):
        Honor.objects.create(title='系统设计竞赛一等奖', contest='系统设计竞赛', level=30, year=2026, awardee='演示一队')
        self.save(title='系统设计竞赛 一等奖')
        with self.assertRaises(ValidationError):
            self.publish()
        self.assertEqual(Honor.summary()['total'], 1)
        self.save(awardee='另一支不同队伍')
        self.publish()
        self.assertEqual(Honor.summary()['total'], 2)

    def test_year_before_importance_and_no_count_per_person(self):
        self.save(contributors=[{'name': '甲'}, {'name': '乙'}])
        self.publish()
        old = Honor.objects.create(title='更早的奖', year=2025, importance=100, level=30)
        self.assertEqual(Honor.wall().first().pk, self.draft.honor_id)
        self.assertEqual(Honor.summary()['total'], 2)
        self.assertEqual(Honor.summary()['national'], 2)

    def test_account_downgrade_hides_and_recovery_requires_republish(self):
        self.save()
        self.publish()
        type(self.owner).objects.filter(pk=self.owner.pk).update(member_level=1)
        self.assertFalse(Honor.objects.public().exists())
        type(self.owner).objects.filter(pk=self.owner.pk).update(member_level=3)
        self.assertFalse(Honor.objects.public().exists())
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.published)

    def test_related_private_project_and_private_story_do_not_leak(self):
        project = Project.objects.create(name='应被隐藏的项目标题', is_public=True)
        self.save(project=project.pk)
        self.publish()
        self.assertContains(Client().get(project.public_url), '系统设计竞赛一等奖')
        self.assertContains(Client().get('/honors/'), project.name)
        project.is_public = False
        project.save()
        self.assertNotContains(Client().get('/honors/'), project.name)
        h = self.draft.honor
        h.post = Post.objects.create(title='内部喜报', min_level=3, body='私密')
        h.save()
        self.assertEqual(h.story_url, '')

    def test_all_new_screens_render_and_do_not_leak_archives(self):
        self.owner.real_name = '不要公开的档案姓名'
        self.owner.save()
        self.save()
        for path in ('/achievements/', '/achievements/catalog/', '/achievements/honors/', reverse('achievements:honor_edit', args=[self.draft.pk]), reverse('achievements:honor_preview', args=[self.draft.pk])):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.publish()
        self.assertNotContains(Client().get('/honors/'), self.owner.real_name)

    def test_lookup_only_exposes_usernames_and_requires_creator(self):
        self.owner.real_name = '私密姓名'
        self.owner.phone = '10000000001'
        self.owner.save()
        response = self.client.get('/achievements/people/?q=own')
        self.assertEqual(response.json(), {'usernames': ['owner']})
        self.assertNotContains(response, '10000000001')
        self.client.force_login(make_user('low', 1))
        self.assertEqual(self.client.get('/achievements/people/?q=own').status_code, 403)


class ContributionContinuityTests(TestCase):
    def setUp(self):
        self.owner, self.other, self.staff = make_user('owner'), make_user('other'), make_user('staff', 4)
        self.work = work_services.create_work(self.owner)
        self.data = {'name': '共享作品', 'year': 2026, 'department': 'other', 'credit': '同一支队伍', 'highlight': '',
                     'summary': '', 'tags': '', 'external_url': '', 'cover': '', 'gallery': [], 'contributors': [{'name': '同名成员', 'role': '软件', 'username': 'other'}]}

    def save(self, data=None):
        self.work = work_services.save_work(self.owner, self.work.pk, self.work.version, deepcopy(data or self.data))

    def publish(self):
        self.work = work_services.publish_work(self.owner, self.work.pk, work_services.preview_token(self.work), 'on')

    def test_work_contributors_only_after_publish_and_no_auto_identity(self):
        self.save()
        self.assertFalse(Contributor.objects.exists())
        self.publish()
        person = self.work.project.contributors.get()
        self.assertIsNone(person.user_id)
        self.assertEqual(person.invited_user_id, self.other.pk)
        self.assertContains(Client().get(self.work.project.public_url), '同名成员')
        services.respond_invitation(self.other, person.pk, True)
        self.assertFalse(self.work.project.members.exists())

    def test_declined_invitation_is_not_resent_by_republishing(self):
        self.save()
        self.publish()
        person = self.work.project.contributors.get()
        services.respond_invitation(self.other, person.pk, False)
        self.save(self.work.draft)
        self.publish()
        person.refresh_from_db()
        self.assertTrue(person.invitation_declined)
        self.assertIsNone(person.user_id)

    def test_removed_credit_does_not_return_after_withdraw_and_republish(self):
        self.save()
        self.publish()
        person = self.work.project.contributors.get()
        work_services.withdraw_work(self.owner, self.work.pk, self.work.version)
        self.work.refresh_from_db()
        self.save({**self.work.draft, 'contributors': []})
        self.publish()
        person.refresh_from_db()
        self.assertFalse(person.active)
        self.assertNotContains(Client().get(self.work.project.public_url), '同名成员')

    def test_claim_added_outside_owner_draft_survives_republish(self):
        self.save({**self.data, 'contributors': []})
        self.publish()
        c = services.request_claim(self.other, 'work', self.work.project_id, None, '补录成员', '算法', '说明')
        services.review_claim(self.staff, c.pk, 'approved', '已核验')
        self.save(self.work.draft)
        self.publish()
        self.assertContains(Client().get(self.work.project.public_url), '补录成员')

    def test_confirmed_credit_cannot_be_reassigned_or_renamed(self):
        self.save()
        self.publish()
        person = self.work.project.contributors.get()
        services.respond_invitation(self.other, person.pk, True)
        data = deepcopy(self.work.draft)
        data['contributors'][0]['name'] = '冒名者'
        self.save(data)
        with self.assertRaises(ValidationError):
            self.publish()
        self.assertNotContains(Client().get(self.work.project.public_url), '冒名者')

    def test_two_same_name_people_can_be_distinguished_by_cohort(self):
        self.save({**self.data, 'contributors': [{'name': '同名', 'cohort': '2024'}, {'name': '同名', 'cohort': '2025'}]})
        self.publish()
        self.assertEqual(self.work.project.contributors.count(), 2)

    def test_duplicate_account_rows_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.save({**self.data, 'contributors': [{'name': '甲', 'username': 'other'}, {'name': '乙', 'username': 'other'}]})

    def test_duplicate_work_is_blocked_without_extra_public_project(self):
        Project.objects.create(name='共享作品', work_year=2026, public_credit='同一支队伍', is_public=True)
        self.save()
        with self.assertRaises(ValidationError):
            self.publish()
        self.assertEqual(Project.public().count(), 1)

    def test_claimed_work_cannot_be_deleted_or_editable_by_claimant(self):
        self.save()
        self.publish()
        services.respond_invitation(self.other, self.work.project.contributors.get().pk, True)
        client = Client()
        client.force_login(self.other)
        self.assertEqual(client.get(reverse('works:edit', args=[self.work.pk])).status_code, 404)
        work_services.withdraw_work(self.owner, self.work.pk, self.work.version)
        self.work.refresh_from_db()
        with self.assertRaises(ValidationError):
            work_services.delete_work(self.owner, self.work.pk, self.work.version)

    def test_people_formset_limits_and_no_javascript_path(self):
        rows = people_set({'people-TOTAL_FORMS': '1', 'people-INITIAL_FORMS': '0', 'people-0-name': '未注册成员', 'people-0-role': '硬件'}, [])
        self.assertTrue(rows.is_valid(), rows.errors)
        data = people_data(rows, [])
        self.assertIsNone(data[0]['account'])
        self.assertTrue(data[0]['id'])
        excessive = people_set({'people-TOTAL_FORMS': '99999', 'people-INITIAL_FORMS': '0'}, [])
        self.assertEqual(len(excessive.forms), 20)
        self.assertFalse(excessive.is_valid())
