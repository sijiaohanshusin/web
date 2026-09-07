import json
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings, Client
from django.utils import timezone
from django.urls import reverse

from projects.tests import make_user, make_cover
from . import honor_services


class RecognitionTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.config = override_settings(MEDIA_ROOT=self.media.name, HONOR_AI_ENABLED=True,
            DASHSCOPE_API_KEY='test-not-a-real-key', DASHSCOPE_WORKSPACE_ID='test-space',
            HONOR_AI_FREE_TIER_CONFIRMED=True,
            HONOR_AI_FREE_TIER_EXPIRES=(timezone.now() + timedelta(days=2)).isoformat())
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.owner, self.other = make_user('recognizer'), make_user('not-owner')
        self.draft = honor_services.create(self.owner)
        from .models import RecognitionGate
        RecognitionGate.objects.get_or_create(pk=1)
        self.client.force_login(self.owner)

    def upload(self):
        response = self.client.post(reverse('achievements:certificate_upload', args=[self.draft.pk]),
            {'version': self.draft.version, 'upload': make_cover()})
        self.assertEqual(response.status_code, 201)
        self.draft.refresh_from_db()
        return response.json()['image']['id']

    def start(self, image, **extra):
        return self.client.post(reverse('achievements:recognition_start', args=[self.draft.pk]),
            {'image': image, 'consent': 'on', **extra})

    def test_certificate_first_does_not_fill_or_publish(self):
        image = self.upload()
        self.assertEqual(self.draft.draft, {})
        self.assertIsNone(self.draft.published)
        self.assertEqual(Client().get(reverse('achievements:certificate', args=[image])).status_code, 404)

    def test_ownership_disabled_and_consent(self):
        image = self.upload()
        with override_settings(HONOR_AI_ENABLED=False):
            self.assertEqual(self.start(image).status_code, 503)
        self.assertEqual(self.start(image, consent='').status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.start(image).status_code, 404)

    def test_dedup_worker_and_private_result(self):
        from . import recognition
        from .models import RecognitionTask
        image = self.upload()
        first, second = self.start(image), self.start(image)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()['id'], second.json()['id'])
        raw = {'title': '全国电子竞赛 省赛一等奖', 'contest': '全国电子竞赛', 'year': '2026',
            'year_evidence': '2026年全国电子竞赛',
            'level': '省级', 'level_evidence': '省赛一等奖', 'awardee': '演示队',
            'contributors': [{'name': '演示甲', 'role': '队员', 'username': 'admin'}]}
        with patch.object(recognition, 'call_model', return_value=(raw, {'input_tokens': 123, 'output_tokens': 67})) as call:
            self.assertTrue(recognition.process_one())
            self.assertFalse(recognition.process_one())
            call.assert_called_once()
        task = RecognitionTask.objects.get(pk=first.json()['id'])
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result['fields']['level'], '20')
        self.assertNotIn('username', task.result['contributors'][0])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.draft, {})
        url = first.json()['status_url']
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertIn('no-store', self.client.get(url).headers.get('Cache-Control', ''))

    def test_missing_or_unreliable_fields_are_not_invented(self):
        from .recognition import normalize_result
        data = normalize_result({'title': '全国测试赛', 'year': '签发于2026', 'level': '国家级',
            'level_evidence': '全国测试赛', 'contributors': [{'name': '李?', 'role': '队员'}],
            'note': '<script>alert(1)</script>', 'certificate_number': 'PRIVATE-ID'})
        self.assertNotIn('year', data['fields'])
        self.assertNotIn('level', data['fields'])
        self.assertEqual(data['contributors'], [])
        self.assertNotIn('script', str(data))
        self.assertNotIn('PRIVATE-ID', str(data))
        self.assertTrue(data['warnings'])

    def test_teacher_list_is_preserved_without_creating_participants(self):
        from .recognition import normalize_result
        data = normalize_result({'title': '示例竞赛一等奖', 'teachers': ['演示导师甲', '演示导师乙'],
                                 'contributors': [{'name': '演示成员', 'role': '参赛队员'}]})
        self.assertEqual(data['fields']['note'], '指导教师：演示导师甲、演示导师乙')
        self.assertEqual(len(data['contributors']), 1)
        unsafe = normalize_result({'title': '示例竞赛一等奖', 'teachers': ['安全导师', '<script>bad</script>']})
        self.assertNotIn('note', unsafe['fields'])
        self.assertTrue(any('指导教师' in warning for warning in unsafe['warnings']))

    def test_year_requires_explicit_event_evidence_not_issuance_or_academic_range(self):
        from .recognition import normalize_result
        for evidence in (None, '2010年12月12日', '签发于2010年', '2010–2011学年度五四表彰',
                         '2011年度创新竞赛', '颁发日期：2010-12-12'):
            with self.subTest(evidence=evidence):
                result = normalize_result({'title': '示例奖项', 'year': '2010', 'year_evidence': evidence})
                self.assertNotIn('year', result['fields'])
        for evidence in ('第九届（2026）全国大学生测试竞赛', '2026 Interdisciplinary Contest In Modeling'):
            result = normalize_result({'title': '示例奖项', 'year': '2026', 'year_evidence': evidence})
            self.assertEqual(result['fields']['year'], '2026')

    def test_empty_recognition_is_not_presented_as_success(self):
        from .recognition import normalize_result, RecognitionError
        with self.assertRaises(RecognitionError) as caught:
            normalize_result({})
        self.assertEqual(caught.exception.code, 'invalid')

    def test_small_image_names_require_explicit_adoption(self):
        from .recognition import normalize_result
        sample = {'title': '校内表彰', 'awardee': '待核对的名字',
                  'contributors': [{'name': '待核对的名字', 'role': ''}]}
        low = normalize_result(sample, image_size=(307, 433))
        self.assertEqual(set(low['review_fields']), {'awardee', 'contributors'})
        self.assertTrue(any('分辨率' in warning for warning in low['warnings']))
        normal = normalize_result(sample, image_size=(1000, 700))
        self.assertEqual(normal['review_fields'], [])

    def test_quota_error_stops_new_calls_and_preserves_input(self):
        from . import recognition
        image = self.upload()
        self.start(image)
        with patch.object(recognition, 'call_model', side_effect=recognition.RecognitionError('quota')):
            recognition.process_one()
        self.assertEqual(self.start(image).status_code, 503)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.draft, {})

    def test_expiry_rate_limit_stale_upload_and_image_removal(self):
        image = self.upload()
        with override_settings(HONOR_AI_FREE_TIER_EXPIRES='2000-01-01T00:00:00+00:00'):
            self.assertEqual(self.start(image).status_code, 503)
        with override_settings(HONOR_AI_USER_DAILY_LIMIT=0):
            self.assertEqual(self.start(image).status_code, 429)
        stale = self.client.post(reverse('achievements:certificate_upload', args=[self.draft.pk]),
            {'version': 0, 'upload': make_cover()})
        self.assertEqual(stale.status_code, 409)
        self.start(image)
        honor_services.remove_image(self.owner, self.draft.pk, self.draft.version, image)
        from .recognition import process_one
        with patch('achievements.recognition.call_model') as call:
            self.assertFalse(process_one())
            call.assert_not_called()

    def test_csrf_and_unqualified_member(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = reverse('achievements:certificate_upload', args=[self.draft.pk])
        self.assertEqual(client.post(url, {'upload': make_cover(), 'version': 0}).status_code, 403)
        self.owner.member_level = 1
        self.owner.save()
        self.assertEqual(self.client.post(url, {'upload': make_cover(), 'version': 0}).status_code, 403)

    def test_deleted_task_does_not_reset_daily_limit(self):
        from .models import RecognitionTask
        image = self.upload()
        with override_settings(HONOR_AI_USER_DAILY_LIMIT=1):
            self.assertEqual(self.start(image).status_code, 202)
            RecognitionTask.objects.all().delete()
            self.assertEqual(self.start(image).status_code, 429)

    def test_retention_and_timeout_are_distinct_from_quota_expiry(self):
        from . import recognition
        from .models import RecognitionTask
        image = self.upload()
        task = self.start(image).json()
        RecognitionTask.objects.filter(pk=task['id']).update(status='succeeded', result={'fields': {'title': 'PRIVATE'}},
            created_at=timezone.now()-timedelta(hours=25))
        response = self.client.get(task['status_url']).json()
        self.assertEqual(response['result'], {})
        self.assertIn('24小时', response['error'])
        recognition.cleanup()
        self.assertEqual(RecognitionTask.objects.get(pk=task['id']).result, {})
        new = self.start(image).json()
        self.assertNotEqual(task['id'], new['id'])
        RecognitionTask.objects.filter(pk=new['id']).update(status='running', started_at=timezone.now()-timedelta(seconds=121))
        with patch.object(recognition, 'call_model') as call:
            self.assertFalse(recognition.process_one())
            call.assert_not_called()
        self.assertEqual(RecognitionTask.objects.get(pk=new['id']).error_code, 'timeout')

    def test_qualification_changed_during_call_discards_result(self):
        from . import recognition
        from .models import RecognitionTask
        task = self.start(self.upload()).json()
        def deactivate(_):
            type(self.owner).objects.filter(pk=self.owner.pk).update(is_active=False)
            return {'title': 'Do not deliver'}, {}
        with patch.object(recognition, 'call_model', side_effect=deactivate):
            recognition.process_one()
        stored = RecognitionTask.objects.get(pk=task['id'])
        self.assertEqual(stored.result, {})
        self.assertEqual(stored.error_code, 'ineligible')

    def test_deleted_certificate_cannot_resurrect_task_during_completion(self):
        from . import recognition
        from .models import Certificate, RecognitionGate, RecognitionTask
        image = self.upload()
        self.start(image)
        checks = 0

        def eligible(_):
            nonlocal checks
            checks += 1
            if checks == 2:
                # Simulate deletion after the worker read its final task snapshot.
                Certificate.objects.get(pk=image).delete()
            return True

        with patch.object(recognition, 'can_publish_work', side_effect=eligible), patch.object(
                recognition, 'call_model', return_value=({'title': 'Local certificate'}, {})):
            self.assertTrue(recognition.process_one())
        self.assertEqual(checks, 2)
        self.assertFalse(RecognitionTask.objects.exists())
        self.assertIsNone(RecognitionGate.objects.get(pk=1).lease)

    def test_malformed_image_and_unconfirmed_quota_never_queue(self):
        response = self.start('not-a-uuid')
        self.assertEqual(response.status_code, 400)
        image = self.upload()
        with override_settings(HONOR_AI_FREE_TIER_CONFIRMED=False):
            self.assertEqual(self.start(image).status_code, 503)
        with override_settings(DASHSCOPE_WORKSPACE_ID='evil.example/path'):
            self.assertEqual(self.start(image).status_code, 503)

    def provider_response(self, task, data, status=200):
        from .recognition import call_model
        from unittest.mock import MagicMock
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [json.dumps(data).encode()]
        response.__enter__.return_value = response
        with patch('achievements.recognition.requests.post', return_value=response) as call:
            result = call_model(task)
        return result, call.call_args

    def test_multimodal_protocol_no_public_url_and_structured_output(self):
        from .models import RecognitionTask
        task = RecognitionTask.objects.get(pk=self.start(self.upload()).json()['id'])
        (result, usage), call = self.provider_response(task, {
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"year":"2026"}'}}],
            'usage': {'total_tokens': 456, 'provider_private': 'not returned'}})
        self.assertEqual(result, {'year': '2026'})
        self.assertEqual(usage['total_tokens'], 456)
        self.assertNotIn('provider_private', usage)
        self.assertEqual(call.args[0], 'https://test-space.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions')
        payload = call.kwargs['json']
        self.assertEqual(payload['model'], 'qwen3.7-flash')
        self.assertEqual(payload['response_format']['type'], 'json_object')
        self.assertTrue(payload['messages'][1]['content'][0]['image_url']['url'].startswith('data:image/jpeg;base64,'))
        self.assertFalse(call.kwargs['allow_redirects'])

    def test_provider_errors_do_not_echo_body_or_key(self):
        from .recognition import RecognitionError
        from .models import RecognitionTask
        task = RecognitionTask.objects.get(pk=self.start(self.upload()).json()['id'])
        for data, status, code in [
            ({'error': {'code': 'AllocationQuota.FreeTierOnly', 'message': 'PRIVATE_PROVIDER_BODY'}}, 403, 'quota'),
            ({'error': {'message': 'PRIVATE_PROVIDER_BODY'}}, 401, 'configuration'),
            ({'choices': [{'finish_reason': 'length', 'message': {'content': 'PRIVATE_PROVIDER_BODY'}}]}, 200, 'invalid'),
            ({'choices': [{'finish_reason': 'stop', 'message': {'content': 'PRIVATE_PROVIDER_BODY'}}]}, 200, 'invalid'),
        ]:
            with self.subTest(code=code), self.assertRaises(RecognitionError) as caught:
                self.provider_response(task, data, status)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('PRIVATE_PROVIDER_BODY', str(caught.exception))
            self.assertNotIn('test-not-a-real-key', str(caught.exception))

    def test_official_general_endpoint_without_workspace(self):
        from . import recognition
        from .models import RecognitionTask
        with override_settings(DASHSCOPE_WORKSPACE_ID=''):
            self.assertEqual(recognition.available(), '')
            task = RecognitionTask.objects.get(pk=self.start(self.upload()).json()['id'])
            _, call = self.provider_response(task, {
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]})
            self.assertEqual(call.args[0], 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')
            with override_settings(HONOR_AI_FREE_TIER_CONFIRMED=False):
                self.assertEqual(recognition.available(), 'configuration')

    def test_invalid_workspace_is_rejected_before_network(self):
        from . import recognition
        from .models import RecognitionTask
        task = RecognitionTask.objects.get(pk=self.start(self.upload()).json()['id'])
        with override_settings(DASHSCOPE_WORKSPACE_ID='evil.example/path'), patch(
                'achievements.recognition.requests.post') as call:
            with self.assertRaises(recognition.RecognitionError):
                recognition.call_model(task)
            call.assert_not_called()
