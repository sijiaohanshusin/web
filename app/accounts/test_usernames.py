import jwt

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import NewMemberRegisterForm, ReturningMemberRegisterForm
from .models import ReturningMembershipRequest, User


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FlexibleUsernameTests(TestCase):
    def payload(self, username, **extra):
        return {
            'username': username, 'real_name': '演示成员', 'student_id': '2026000198',
            'college': '信息与通信工程学院', 'grade': '2026',
            'specialty': User.Specialty.SOFTWARE, 'email': 'demo-name@example.com',
            'phone': '13800000198', 'code': '123456', 'privacy_consent': True,
            'password1': 'Only-Local-Test-2026!', 'password2': 'Only-Local-Test-2026!',
            'requested_role': ReturningMembershipRequest.RequestedRole.MEMBER, **extra,
        }

    def test_both_channels_allow_chinese_and_supported_punctuation(self):
        for form_class in (NewMemberRegisterForm, ReturningMemberRegisterForm):
            for name in ('林序', '焊板的小林', '林序.dev', 'HEU-ESTA', 'C++新手', 'name_2026', '会' * 20):
                with self.subTest(channel=form_class.__name__, name=name):
                    form = form_class(self.payload(name))
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.cleaned_data['username'], name)

    def test_rejects_unsupported_invisible_or_punctuation_only_names(self):
        for name in ('甲', '会' * 21, '小 林', 'a/b', 'a@b', '<b>甲</b>', '测试😀', 'a\u200bb',
                     'a\u202eb', 'a\tb', 'a\nb', '....', '_-++'):
            with self.subTest(name=name):
                form = NewMemberRegisterForm(self.payload(name))
                self.assertFalse(form.is_valid())
                self.assertIn('username', form.errors)

    def test_normalizes_full_width_and_rejects_existing_equivalent(self):
        form = NewMemberRegisterForm(self.payload('Ｃ＋＋新手'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['username'], 'C++新手')
        form.save()
        other = NewMemberRegisterForm(self.payload('ｃ＋＋新手', email='another@example.com',
                                                    student_id='2026000199', phone='13800000199'))
        self.assertFalse(other.is_valid())
        self.assertIn('username', other.errors)

    def test_new_username_logs_in_and_resolves_in_member_picker(self):
        form = NewMemberRegisterForm(self.payload('林序.dev+'))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        cache.clear()
        response = self.client.post(reverse('accounts:login'), {
            'username': '林序.dev+', 'password': self.payload('unused')['password1'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(User.find_by_identifier('林序.dev+'), [user])

    @override_settings(NODEBB_JWT_SECRET='isolated-username-sso-test-32-characters')
    def test_sso_keeps_id_and_unicode_username_without_changing_eligibility(self):
        user = User.objects.create_user(username='C++新手', member_level=1)
        self.client.force_login(user)
        response = self.client.get(reverse('accounts:profile'))
        from django.conf import settings
        self.assertNotIn(settings.SSO_COOKIE_NAME, response.cookies)
        user.member_level = 3
        user.save(update_fields=['member_level'])
        response = self.client.get(reverse('accounts:profile'))
        payload = jwt.decode(response.cookies[settings.SSO_COOKIE_NAME].value,
                             'isolated-username-sso-test-32-characters', algorithms=['HS256'])
        self.assertEqual(payload['username'], 'C++新手')
        self.assertEqual(payload['id'], user.pk)

    def test_both_register_pages_show_the_same_rule(self):
        for route in ('accounts:register_new', 'accounts:register_returning'):
            page = self.client.get(reverse(route))
            self.assertContains(page, '2–20 个字符')
            self.assertNotContains(page, '4-20 位字母')
