"""Run with python -m unittest discover -s ops/shared-mail -p test_*.py."""
import email
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

TEMP = tempfile.TemporaryDirectory()
os.environ['SHARED_MAIL_LOCAL'] = '1'
os.environ['SHARED_MAIL_CONFIG'] = str(Path(TEMP.name) / 'config.json')
from django.contrib.auth.hashers import PBKDF2PasswordHasher
Path(os.environ['SHARED_MAIL_CONFIG']).write_text(json.dumps({
    'starts_at': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    'session_secret': 'isolated-test-secret-only', 'account': 'fixture@example.test',
    'app_password': 'unused-fixture', 'rate_db': str(Path(TEMP.name) / 'rate.sqlite'),
    'password_hash': PBKDF2PasswordHasher().encode('fixture-passphrase', 'test-salt', iterations=1000),
}), encoding='utf-8')
import service
import gmail_transport
from django.test import Client


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        rate = Path(service.CONFIG['rate_db'])
        if rate.exists():
            rate.unlink()

    def login(self):
        return self.client.post('/shared-mail/', {'password': 'fixture-passphrase'})

    def test_login_requires_password_and_does_not_expose_account(self):
        response = self.client.get('/shared-mail/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'fixture@example.test', response.content)
        self.assertEqual(self.client.post('/shared-mail/', {'password': 'wrong'}).status_code, 400)
        self.assertEqual(self.login().status_code, 302)

    def test_every_mail_endpoint_requires_access(self):
        for route in ['inbox/', 'message/5/1/', 'message/5/1/body/']:
            with patch.object(service, 'connect') as connect:
                response = self.client.get('/shared-mail/' + route)
                self.assertEqual(response.status_code, 302)
                connect.assert_not_called()

    def test_csrf_is_enforced_and_uncached(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/shared-mail/', {'password': 'fixture-passphrase'})
        self.assertEqual(response.status_code, 403)
        self.assertIn('no-store', response['Cache-Control'])

    def test_expired_cookie_and_service_both_block(self):
        self.login()
        with patch.object(service, 'active', return_value=False):
            for route in ['', 'inbox/', 'message/5/1/', 'message/5/1/body/']:
                self.assertEqual(self.client.get('/shared-mail/' + route).status_code, 410)
        self.login()
        with patch.object(service.time, 'time', return_value=service.END.timestamp() + 1):
            self.assertEqual(self.client.get('/shared-mail/inbox/').status_code, 302)

    def test_logout_requires_post_and_revokes_session(self):
        self.login()
        self.assertEqual(self.client.get('/shared-mail/logout/').status_code, 405)
        self.client.post('/shared-mail/logout/')
        self.assertEqual(self.client.get('/shared-mail/inbox/').status_code, 302)

    def test_rate_limit(self):
        with patch.object(service, 'check_password', return_value=False):
            for _ in range(20):
                self.assertEqual(self.client.post('/shared-mail/', {'password': 'bad'}).status_code, 400)
            response = self.client.post('/shared-mail/', {'password': 'bad'})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response['Retry-After'], '900')

    def test_mail_headers_escaped_and_errors_hide_secrets(self):
        self.login()
        rows = [{'subject': '<script>bad()</script>', 'sender': '<img onerror=bad()>',
                 'uid': '1', 'validity': '5', 'received': '09-08 18:00'}]
        with patch.object(service, 'list_mail', return_value=rows):
            response = self.client.get('/shared-mail/inbox/')
            self.assertContains(response, '&lt;script&gt;')
            self.assertNotIn(b'<script>', response.content)
        with patch.object(service, 'list_mail', side_effect=RuntimeError('SECRET')):
            response = self.client.get('/shared-mail/inbox/')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'SECRET', response.content)

    def assertContains(self, response, text):
        self.assertIn(text.encode(), response.content)

    def test_all_responses_are_uncached_and_not_indexed(self):
        for url in ['/shared-mail/', '/shared-mail/style.css', '/shared-mail/missing/']:
            response = self.client.get(url)
            self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(response['CDN-Cache-Control'], 'no-store')
            self.assertIn('noindex', response['X-Robots-Tag'])
            self.assertEqual(response['Referrer-Policy'], 'same-origin')

    def test_password_rotation_invalidates_existing_session(self):
        self.login()
        with patch.object(service, 'SESSION_MARKER', 'rotated'):
            self.assertEqual(self.client.get('/shared-mail/inbox/').status_code, 302)

    def test_body_requires_access_and_is_sandboxed(self):
        self.login()
        with patch.object(service, 'get_mail', return_value=({}, '<p>fixture text</p>', [])):
            response = self.client.get('/shared-mail/message/5/1/body/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('sandbox', response['Content-Security-Policy'])
        self.assertNotIn('allow-scripts', response['Content-Security-Policy'])
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')


class MailTests(unittest.TestCase):
    def test_mime_html_sanitizer(self):
        msg = EmailMessage()
        msg.set_content('Plain fallback')
        msg.add_alternative('<h1>Hello</h1><script>STEAL</script><img src="https://tracker.test/1"><svg>BAD</svg><form>FORM</form><p style="background:url(https://tracker.test)">Safe</p><a href="javascript:evil()">bad link</a><a href="https://example.test">safe link</a>', subtype='html')
        body, _ = service.parse_mail(msg.as_bytes())
        self.assertIn('<h1>Hello</h1>', body)
        for value in ['STEAL', 'tracker.test', '<svg', '<form', 'javascript:', 'style=']:
            self.assertNotIn(value, body)
        self.assertIn('target="_blank"', body)
        self.assertIn('noopener', body)

    def test_plain_text_unicode_and_attachments(self):
        msg = EmailMessage()
        msg.set_content('你好 <script>untrusted</script>')
        msg.add_attachment(b'secret', maintype='application', subtype='octet-stream', filename='example.txt')
        body, files = service.parse_mail(msg.as_bytes())
        self.assertIn('你好', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertEqual(files, ['example.txt'])
        self.assertNotIn('secret', body)

    def test_connection_is_tls_and_readonly(self):
        fake = MagicMock()
        fake.select.return_value = ('OK', [])
        with patch.object(service, 'GmailIMAP', return_value=fake) as factory:
            service.connect()
        factory.assert_called_once()
        fake.select.assert_called_once_with('INBOX', readonly=True)
        self.assertEqual(factory.call_args.args[:2], ('imap.gmail.com', 993))
        self.assertIsNotNone(factory.call_args.kwargs['ssl_context'])

    def test_visibility_uses_internaldate_not_forged_date(self):
        fake = MagicMock()
        fake.response.return_value = ('UIDVALIDITY', [b'5'])
        old = (service.START - timedelta(hours=2)).strftime('%d-%b-%Y %H:%M:%S %z')
        new = (service.START + timedelta(minutes=1)).strftime('%d-%b-%Y %H:%M:%S %z')
        fake.uid.side_effect = [
            ('OK', [b'1 2']),
            ('OK', [f'1 (UID 1 INTERNALDATE "{old}" RFC822.SIZE 100)'.encode(),
                    f'2 (UID 2 INTERNALDATE "{new}" RFC822.SIZE 100)'.encode()]),
            ('OK', [(b'2 (UID 2 BODY[HEADER.FIELDS (SUBJECT FROM DATE)] {24}', b'Subject: New\r\nFrom: A\r\n\r\n'), b')']),
        ]
        validity, rows = service.visible_rows(fake)
        self.assertEqual(validity, '5')
        self.assertEqual([row['uid'] for row in rows], ['2'])
        self.assertEqual(rows[0]['subject'], 'New')
        self.assertIn('BODY.PEEK', str(fake.uid.call_args))
        self.assertNotIn('STORE', str(fake.uid.call_args_list))

    def test_guessed_historical_uid_and_validity_rejected(self):
        fake = MagicMock()
        with patch.object(service, 'connect', return_value=fake), patch.object(service, 'visible_rows', return_value=('5', [])):
            with self.assertRaises(service.Http404):
                service.get_mail('5', '99')
            fake.uid.assert_not_called()
        with patch.object(service, 'connect', return_value=fake), patch.object(service, 'visible_rows', return_value=('6', [{'uid': '1', 'size': 10}])):
            with self.assertRaises(service.Http404):
                service.get_mail('5', '1')

    def test_large_message_not_downloaded(self):
        fake = MagicMock()
        row = {'uid': '1', 'size': service.MAX_BYTES + 1}
        with patch.object(service, 'connect', return_value=fake), patch.object(service, 'visible_rows', return_value=('5', [row])):
            _, body, _ = service.get_mail('5', '1')
            self.assertIn('5MB', body)
            fake.uid.assert_not_called()

    def test_busy_mailbox_does_not_queue_web_requests_indefinitely(self):
        with patch.object(service, 'IMAP_LOCK') as lock:
            lock.acquire.return_value = False
            with self.assertRaises(TimeoutError):
                service.list_mail()
            lock.acquire.assert_called_once_with(timeout=1)
            lock.release.assert_not_called()


class TransportTests(unittest.TestCase):
    def setUp(self):
        gmail_transport.DNS_CACHE.update(until=0, addresses=[])

    def test_encrypted_dns_rejects_private_addresses(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'Status': 0, 'Answer': [
            {'type': 1, 'data': '127.0.0.1'}, {'type': 1, 'data': '10.0.0.1'},
            {'type': 1, 'data': '142.250.107.108'}]}).encode()
        with patch.object(gmail_transport, 'urlopen', return_value=response) as query:
            self.assertEqual(gmail_transport.addresses(), ['142.250.107.108'])
            self.assertEqual(gmail_transport.addresses(), ['142.250.107.108'])
        query.assert_called_once()

    def test_dns_failure_uses_canonical_system_resolution(self):
        with patch.object(gmail_transport, 'urlopen', side_effect=TimeoutError):
            self.assertEqual(gmail_transport.addresses(), ['imap.gmail.com'])

    def test_tls_still_verifies_gmail_hostname(self):
        instance = object.__new__(gmail_transport.GmailIMAP)
        instance.deadline = service.time.monotonic() + 18
        instance.host, instance.port = 'imap.gmail.com', 993
        instance.ssl_context = MagicMock()
        sock = MagicMock()
        with patch.object(gmail_transport, 'addresses', return_value=['142.250.107.108']), patch.object(gmail_transport.socket, 'create_connection', return_value=sock):
            instance._create_socket(10)
        instance.ssl_context.wrap_socket.assert_called_once_with(sock, server_hostname='imap.gmail.com')

    def test_imap_total_deadline_clears_unreachable_dns_cache(self):
        instance = object.__new__(gmail_transport.GmailIMAP)
        instance.deadline = service.time.monotonic() - 1
        gmail_transport.DNS_CACHE.update(until=999999999, addresses=['142.250.107.108'])
        with self.assertRaises(TimeoutError):
            instance.remaining()
        self.assertEqual(gmail_transport.DNS_CACHE['until'], 0)

    def test_expiry_during_fetch_is_also_blocked(self):
        client = Client()
        client.post('/shared-mail/', {'password': 'fixture-passphrase'})
        with patch.object(service, 'active', side_effect=[True, False]), patch.object(service, 'list_mail', return_value=[]):
            response = client.get('/shared-mail/inbox/')
        self.assertEqual(response.status_code, 410)


if __name__ == '__main__':
    unittest.main()
