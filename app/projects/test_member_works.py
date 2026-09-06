import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import MemberWork, Project, WorkImage
from .tests import make_user, make_cover


class MemberWorksTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.owner = make_user('work-owner')
        self.other = make_user('work-other')
        self.officer = make_user('work-officer', 4)
        self.client.force_login(self.owner)
        self.work = MemberWork.objects.create(owner=self.owner)

    def edit_url(self):
        return reverse('works:edit', args=[self.work.pk])

    def payload(self, **changes):
        self.work.refresh_from_db()
        data = {'name': '便携信号源', 'summary': '从电路到固件的制作记录。',
                'highlight': '可随身携带的测量工具', 'department': 'hardware',
                'year': '2026', 'credit': '公开署名', 'tags': 'STM32, PCB',
                'external_url': 'https://example.com/demo', 'version': self.work.version,
                'action': 'save'}
        data.update(changes)
        return data

    def save(self, **changes):
        return self.client.post(self.edit_url(), self.payload(**changes))

    def publish(self):
        preview = self.client.get(reverse('works:preview', args=[self.work.pk]))
        self.assertEqual(preview.status_code, 200)
        return self.client.post(reverse('works:publish', args=[self.work.pk]), {
            'token': preview.context['publish_token'], 'consent': 'on',
        })

    def test_member_creates_and_publishes_without_approval(self):
        self.assertEqual(self.save().status_code, 302)
        self.assertEqual(Project.public().count(), 0)
        self.assertEqual(self.publish().status_code, 302)
        self.work.refresh_from_db()
        self.assertEqual(Project.public().get().pk, self.work.project_id)
        self.client.logout()
        detail = self.client.get(self.work.project.public_url)
        self.assertContains(detail, '便携信号源')
        self.assertContains(detail, '公开署名')
        self.assertNotContains(detail, self.owner.username)

    def test_wall_explains_member_upload_destination(self):
        response = self.client.get(reverse('works:wall'))
        self.assertContains(response, reverse('works:mine'))
        self.assertContains(response, '发布后直接出现在协会作品墙，无需站务审批。')
        self.save()
        preview = self.client.get(reverse('works:preview', args=[self.work.pk]))
        self.assertContains(preview, '确认后直接发布到协会作品墙')

    def test_wall_follows_author_publication_snapshot_and_withdrawal(self):
        visitor = Client()
        wall = reverse('works:wall')
        self.save(upload=make_cover())
        self.assertNotContains(visitor.get(wall), '便携信号源')
        self.publish()
        self.work.refresh_from_db()
        response = visitor.get(wall)
        self.assertContains(response, '便携信号源')
        self.assertContains(response, self.work.project.public_url)
        self.assertEqual(response.context['total'], 1)
        self.save(name='作者更新后的公开作品')
        response = visitor.get(wall)
        self.assertContains(response, '便携信号源')
        self.assertNotContains(response, '作者更新后的公开作品')
        self.publish()
        self.assertContains(visitor.get(wall), '作者更新后的公开作品')
        self.assertNotContains(visitor.get(wall), '便携信号源')
        self.work.refresh_from_db()
        self.client.post(reverse('works:withdraw', args=[self.work.pk]), {
            'version': self.work.version, 'confirm': 'on',
        })
        response = visitor.get(wall)
        self.assertNotContains(response, '作者更新后的公开作品')
        self.assertEqual(response.context['total'], 0)

    def test_draft_edits_do_not_change_live_content(self):
        self.save()
        self.publish()
        self.work.refresh_from_db()
        self.save(name='新私有草稿')
        detail = self.client.get(self.work.project.public_url)
        self.assertContains(detail, '便携信号源')
        self.assertNotContains(detail, '新私有草稿')
        self.publish()
        self.assertContains(self.client.get(self.work.project.public_url), '新私有草稿')

    def test_only_owner_can_edit_preview_or_withdraw(self):
        self.save()
        self.publish()
        for user in (self.other, self.officer):
            self.client.force_login(user)
            for name in ('edit', 'preview'):
                self.assertEqual(self.client.get(reverse('works:' + name, args=[self.work.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse('works:withdraw', args=[self.work.pk])).status_code, 404)

    def test_qualification_and_get_do_not_create_records(self):
        for level in (0, 1, 2):
            self.client.force_login(make_user('new-' + str(level), level))
            self.assertEqual(self.client.post(reverse('works:create')).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('works:create')).status_code, 405)
        self.assertEqual(MemberWork.objects.count(), 1)

    def test_conflicting_save_keeps_server_version(self):
        stale = self.payload()
        self.save(name='先保存的版本')
        response = self.client.post(self.edit_url(), {**stale, 'name': '过时标签页'})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, '过时标签页', status_code=409)
        self.work.refresh_from_db()
        self.assertEqual(self.work.draft['name'], '先保存的版本')

    def test_publish_needs_consent_and_fresh_owner_preview(self):
        self.save()
        url = reverse('works:publish', args=[self.work.pk])
        token = self.client.get(reverse('works:preview', args=[self.work.pk])).context['publish_token']
        self.assertEqual(self.client.post(url, {'token': token}).status_code, 400)
        self.save(name='已修改')
        self.assertEqual(self.client.post(url, {'token': token, 'consent': 'on'}).status_code, 409)
        self.assertEqual(self.client.post(url, {'token': 'fake', 'consent': 'on'}).status_code, 400)
        self.assertFalse(Project.public().exists())

    def test_member_cannot_change_importance_or_featured(self):
        self.save(importance=100, is_featured='on')
        self.publish()
        project = Project.public().get()
        self.assertEqual(project.importance, 0)
        self.assertFalse(project.is_featured)
        self.assertEqual(self.client.post(reverse('works:ranking'), {'project': project.pk, 'importance': 99}).status_code, 403)

    def test_officer_ranks_but_cannot_publish_or_edit_member_content(self):
        self.save()
        self.publish()
        project = Project.public().get()
        self.client.force_login(self.officer)
        response = self.client.post(reverse('works:ranking'), {
            'project': project.pk, 'importance': 75, 'is_featured': 'on',
            'name': '不应覆盖', 'is_public': ''})
        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.importance, 75)
        self.assertTrue(project.is_public)
        self.assertEqual(project.name, '便携信号源')
        self.assertEqual(self.client.post(reverse('dashboard:project_edit', args=[project.pk]), {'name': '改名'}).status_code, 404)

    def test_sort_year_before_importance_and_not_last_edited(self):
        older = Project.objects.create(name='上一年重要作品', is_public=True, work_year=2025, importance=100)
        regular = Project.objects.create(name='今年一般作品', is_public=True, work_year=2026, importance=0)
        important = Project.objects.create(name='今年重要作品', is_public=True, work_year=2026, importance=60)
        self.assertEqual(list(Project.public()), [important, regular, older])
        regular.save()
        self.assertEqual(list(Project.public()), [important, regular, older])

    def test_wall_counts_all_works_in_the_same_department(self):
        for year in (2024, 2025, 2026):
            Project.objects.create(name=f'硬件作品 {year}', department='hardware', is_public=True, work_year=year)
        response = self.client.get(reverse('works:wall'))
        self.assertEqual(response.context['total'], 3)
        self.assertEqual(response.context['dept_tabs'], [('hardware', '硬件部', 3)])

    @override_settings(DEBUG=True)
    def test_images_protected_until_publication_and_after_withdrawal(self):
        self.save(upload=make_cover())
        asset = WorkImage.objects.get()
        self.assertEqual(self.client.get(asset.public_url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(asset.public_url).status_code, 404)
        self.assertEqual(self.client.get('/media/' + asset.image.name).status_code, 403)
        self.client.force_login(self.owner)
        self.publish()
        self.work.refresh_from_db()
        self.client.logout()
        response = self.client.get(asset.public_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertTrue(b''.join(response.streaming_content))
        self.client.force_login(self.owner)
        response = self.client.post(reverse('works:withdraw', args=[self.work.pk]), {'version': self.work.version, 'confirm': 'on'})
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(self.work.project.public_url).status_code, 404)
        self.assertEqual(self.client.get(asset.public_url).status_code, 404)

    def test_unreferenced_images_stay_private_and_foreign_reference_is_rejected(self):
        self.save(upload=make_cover())
        old = WorkImage.objects.get()
        self.save(cover='', gallery=[])
        self.publish()
        self.client.force_login(self.other)
        theirs = MemberWork.objects.create(owner=self.other)
        response = self.client.post(reverse('works:edit', args=[theirs.pk]), self.payload(version=0, cover=str(old.pk)))
        self.assertEqual(response.status_code, 200)
        theirs.refresh_from_db()
        self.assertFalse(theirs.draft)
        self.client.logout()
        self.assertEqual(self.client.get(old.public_url).status_code, 404)

    def test_active_public_image_cannot_be_deleted_after_draft_removes_it(self):
        self.save(upload=make_cover())
        asset = WorkImage.objects.get()
        self.publish()
        self.save(cover='')
        self.work.refresh_from_db()
        response = self.client.post(reverse('works:delete_image', args=[self.work.pk, asset.pk]), {'version': self.work.version})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(WorkImage.objects.filter(pk=asset.pk).exists())

    def test_invalid_image_and_insecure_link_do_not_save(self):
        self.assertEqual(self.save(upload=SimpleUploadedFile('fake.png', b'<script>bad</script>')).status_code, 200)
        self.assertFalse(WorkImage.objects.exists())
        self.save(external_url='javascript:alert(1)')
        self.work.refresh_from_db()
        self.assertEqual(self.work.draft, {})

    def test_downgrade_does_not_restore_publication_on_upgrade(self):
        self.save()
        self.publish()
        self.owner.set_level(1)
        self.assertFalse(Project.public().exists())
        self.owner.set_level(3)
        self.assertFalse(Project.public().exists())

    def test_bulk_downgrade_cannot_restore_publication(self):
        self.save()
        self.publish()
        users = type(self.owner).objects.filter(pk=self.owner.pk)
        users.update(member_level=1)
        users.update(member_level=3)
        self.assertFalse(Project.public().exists())

    def test_bulk_deactivation_cannot_restore_publication(self):
        self.save()
        self.publish()
        self.owner.is_active = False
        type(self.owner).objects.bulk_update([self.owner], ['is_active'])
        self.owner.is_active = True
        type(self.owner).objects.bulk_update([self.owner], ['is_active'])
        self.assertFalse(Project.public().exists())

    def test_partial_user_save_uses_persisted_qualification(self):
        self.save()
        self.publish()
        self.owner.member_level = 1
        self.owner.first_name = 'Updated'
        self.owner.save(update_fields=['first_name'])
        self.assertTrue(Project.public().exists())

    def test_member_work_does_not_open_project_files_or_expose_drafts_in_archive(self):
        self.save(name='未公开作品秘密')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('projects:list')), '未公开作品秘密')
        self.client.force_login(self.owner)
        self.publish()
        project = Project.public().get()
        self.assertFalse(project.members.exists())
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse('projects:detail', args=[project.pk])).status_code, 403)

    def test_repeat_publish_is_conflict_not_duplicate(self):
        self.save()
        token = self.client.get(reverse('works:preview', args=[self.work.pk])).context['publish_token']
        url = reverse('works:publish', args=[self.work.pk])
        self.assertEqual(self.client.post(url, {'token': token, 'consent': 'on'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'token': token, 'consent': 'on'}).status_code, 409)
        self.assertEqual(Project.objects.count(), 1)

    def test_invalid_ranking_does_not_change_records(self):
        self.save()
        self.publish()
        item = Project.public().get()
        self.client.force_login(self.officer)
        for importance in ('-1', '101', 'not-a-number'):
            self.client.post(reverse('works:ranking'), {'project': item.pk, 'importance': importance})
            item.refresh_from_db()
            self.assertEqual(item.importance, 0)

    def test_post_actions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse('works:create')).status_code, 403)
        self.assertEqual(client.post(self.edit_url(), self.payload()).status_code, 403)

    @override_settings(DEBUG=False)
    def test_production_image_redirect_and_private_cache_headers(self):
        self.save(upload=make_cover())
        asset = WorkImage.objects.get()
        response = self.client.get(asset.public_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/protected/' + asset.image.name)
        self.assertIn('no-store', response['Cache-Control'])
        self.client.logout()
        for url in (asset.public_url, reverse('works:mine'), self.edit_url()):
            self.assertIn('no-store', self.client.get(url)['Cache-Control'])

    def test_static_reencoding_removes_exif_and_rejects_animation(self):
        image = Image.new('RGB', (120, 80), '#24536b')
        exif = Image.Exif()
        exif[0x010E] = 'Private metadata'
        stream = BytesIO()
        image.save(stream, 'JPEG', exif=exif)
        self.save(upload=SimpleUploadedFile('private.jpg', stream.getvalue(), content_type='image/jpeg'))
        asset = WorkImage.objects.get()
        with asset.image.open('rb') as file, Image.open(file) as result:
            self.assertEqual(result.format, 'JPEG')
            self.assertFalse(result.getexif())
        stream = BytesIO()
        image.save(stream, 'PNG', save_all=True, append_images=[Image.new('RGB', (120, 80), '#999999')], duration=100)
        self.save(upload=SimpleUploadedFile('animation.png', stream.getvalue(), content_type='image/png'))
        self.assertEqual(WorkImage.objects.count(), 1)

    def test_unreferenced_image_can_be_deleted_but_public_work_must_be_withdrawn_first(self):
        self.save(upload=make_cover())
        asset = WorkImage.objects.get()
        self.save(cover='')
        self.work.refresh_from_db()
        self.assertEqual(self.client.post(reverse('works:delete_image', args=[self.work.pk, asset.pk]),
            {'version': self.work.version}).status_code, 302)
        self.assertFalse(WorkImage.objects.exists())
        self.publish()
        self.work.refresh_from_db()
        self.assertEqual(self.client.post(reverse('works:delete', args=[self.work.pk]),
            {'version': self.work.version, 'confirm': 'on'}).status_code, 400)
        self.assertTrue(Project.public().exists())
