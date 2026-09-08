"""Isolated, expiring, read-only Gmail viewer. No main-site models or sessions."""
import email
import hashlib
import html
import imaplib
import json
import logging
import os
import re
import sqlite3
import ssl
import threading
import time
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from email import policy
from pathlib import Path

import nh3
from gmail_transport import GmailIMAP
from django.conf import settings

BASE = Path(__file__).resolve().parent
CONFIG = json.loads(Path(os.environ['SHARED_MAIL_CONFIG']).read_text(encoding='utf-8'))
START = datetime.fromisoformat(CONFIG['starts_at'])
END = datetime.fromisoformat(CONFIG['expires_at'])
if START.tzinfo is None or END.tzinfo is None or END <= START:
    raise ValueError('Invalid activation interval')
LOCAL = os.environ.get('SHARED_MAIL_LOCAL') == '1'
settings.configure(
    DEBUG=False, SECRET_KEY=CONFIG['session_secret'], ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=['heuesta.cn'] + (['127.0.0.1', 'localhost', 'testserver'] if LOCAL else []),
    INSTALLED_APPS=[],
    MIDDLEWARE=[
        'service.SecurityHeaders',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
    ],
    SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies',
    SESSION_COOKIE_NAME='heuesta_shared_mail', SESSION_COOKIE_PATH='/shared-mail/',
    SESSION_COOKIE_SECURE=not LOCAL, SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_AGE=8 * 3600,
    CSRF_COOKIE_NAME='heuesta_shared_mail_csrf', CSRF_COOKIE_PATH='/shared-mail/',
    CSRF_COOKIE_SECURE=not LOCAL, CSRF_COOKIE_HTTPONLY=True, CSRF_COOKIE_SAMESITE='Strict',
    CSRF_FAILURE_VIEW='service.csrf_failure',
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [BASE / 'templates']}],
    DATA_UPLOAD_MAX_MEMORY_SIZE=8192, DATA_UPLOAD_MAX_NUMBER_FIELDS=10,
    USE_TZ=True, LANGUAGE_CODE='zh-hans', DEFAULT_CHARSET='utf-8',
    LOGGING={'version': 1, 'disable_existing_loggers': False,
             'handlers': {'null': {'class': 'logging.NullHandler'}},
             'loggers': {'django.request': {'handlers': ['null'], 'propagate': False},
                         'django.security.csrf': {'handlers': ['null'], 'propagate': False}}},
)
import django
django.setup()
from django.contrib.auth.hashers import check_password
from django.core.wsgi import get_wsgi_application
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.http import require_GET, require_http_methods, require_POST

PREFIX = '/shared-mail/'
SESSION_MARKER = hashlib.sha256(CONFIG['password_hash'].encode()).hexdigest()
IMAP_LOCK = threading.Lock()
CACHE = {'until': 0, 'rows': [], 'validity': ''}
MAX_BYTES = 5 * 1024 * 1024
logger = logging.getLogger('shared-mail')


def now():
    return datetime.now(timezone.utc)


def active():
    return START <= now() < END


class SecurityHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(PREFIX + 'inbox/') or request.path.startswith(PREFIX + 'message/'):
            if not active():
                response = page(request, 'login.html', expired=True, status=410)
        response['Cache-Control'] = 'private, no-store, max-age=0, must-revalidate'
        response['CDN-Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['Vary'] = 'Cookie'
        response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        # Same-origin referrers keep browser form POSTs compatible with Django CSRF.
        response.setdefault('Referrer-Policy', 'same-origin')
        response['X-Content-Type-Options'] = 'nosniff'
        response.setdefault('X-Frame-Options', 'DENY')
        response.setdefault('Content-Security-Policy',
            "default-src 'none'; style-src 'self'; script-src 'none'; img-src 'self'; "
            "frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        return response


def page(request, name, **context):
    status = context.pop('status', 200)
    context.update(expires=END.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
                   starts=START.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
                   mailbox=CONFIG['account'])
    return render(request, name, context, status=status)


def denied(request):
    if not active():
        return page(request, 'login.html', expired=True, status=410)
    if (request.session.get('access') != SESSION_MARKER
            or request.session.get('deadline', 0) <= time.time()):
        return redirect(PREFIX)
    return None


def allow_attempt(request):
    # The backend only accepts traffic from the local reverse proxy. Never trust XFF.
    address = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')
    ip_key = hashlib.sha256((CONFIG['session_secret'] + address).encode()).hexdigest()
    bucket = int(time.time()) // 900
    with closing(sqlite3.connect(CONFIG['rate_db'], timeout=3)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS attempts (key TEXT, bucket INTEGER, n INTEGER, PRIMARY KEY(key,bucket))')
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM attempts WHERE bucket < ?', (bucket - 1,))
        for key, limit in [('all', 120), (ip_key, 20)]:
            row = db.execute('SELECT n FROM attempts WHERE key=? AND bucket=?', (key, bucket)).fetchone()
            if row and row[0] >= limit:
                return False
        for key in ['all', ip_key]:
            db.execute('INSERT INTO attempts VALUES (?, ?, 1) ON CONFLICT(key,bucket) DO UPDATE SET n=n+1', (key, bucket))
    return True


def csrf_failure(request, reason=''):
    return page(request, 'login.html', error='页面已过期，请重新打开入口后再输入访问密码。', status=403)


@require_http_methods(['GET', 'POST'])
def index(request):
    if not active():
        request.session.flush()
        return page(request, 'login.html', expired=True, status=410)
    if request.method == 'POST':
        if not allow_attempt(request):
            response = page(request, 'login.html', error='尝试次数较多，请在 15 分钟后重试。', status=429)
            response['Retry-After'] = '900'
            return response
        password = request.POST.get('password', '')
        if len(password) > 128 or not check_password(password, CONFIG['password_hash']):
            return page(request, 'login.html', error='访问密码不正确，请向分享者确认。', status=400)
        request.session.cycle_key()
        request.session['access'] = SESSION_MARKER
        request.session['deadline'] = min(time.time() + 8 * 3600, END.timestamp())
        return redirect(PREFIX + 'inbox/')
    if denied(request) is None:
        return redirect(PREFIX + 'inbox/')
    return page(request, 'login.html')


@require_POST
def logout(request):
    request.session.flush()
    return redirect(PREFIX)


def connect():
    if not active():
        raise RuntimeError('Inactive mailbox')
    connection = GmailIMAP('imap.gmail.com', 993, ssl_context=ssl.create_default_context(), timeout=10)
    try:
        connection.login(CONFIG['account'], CONFIG['app_password'])
        status, _ = connection.select('INBOX', readonly=True)
        if status != 'OK':
            raise RuntimeError('Mailbox unavailable')
        return connection
    except Exception:
        connection.logout()
        raise


def fetch_literal(connection, uid, query):
    status, chunks = connection.uid('FETCH', uid, query)
    if status != 'OK':
        raise RuntimeError('Fetch failed')
    return b''.join(chunk[1] for chunk in chunks if isinstance(chunk, tuple))


def visible_rows(connection):
    validity = connection.response('UIDVALIDITY')[1][0].decode('ascii')
    since = (START - timedelta(days=1)).strftime('%d-%b-%Y')
    status, found = connection.uid('SEARCH', None, 'SINCE', since)
    if status != 'OK':
        raise RuntimeError('Search failed')
    rows = []
    uids = found[0].split()[-100:]
    if not uids:
        return validity, rows
    status, metadata = connection.uid('FETCH', b','.join(uids), '(UID INTERNALDATE RFC822.SIZE)')
    if status != 'OK':
        raise RuntimeError('Metadata fetch failed')
    for raw in metadata:
        if not isinstance(raw, bytes):
            continue
        uid = re.search(rb'UID (\d+)', raw)
        date = re.search(rb'INTERNALDATE "([^"]+)"', raw)
        size = re.search(rb'RFC822.SIZE (\d+)', raw)
        if not uid or not date or not size:
            continue
        received = datetime.strptime(date[1].decode('ascii'), '%d-%b-%Y %H:%M:%S %z')
        if received < START or received >= END:
            continue
        rows.append({'uid': uid[1].decode('ascii'), 'validity': validity,
                     'subject': '（无主题）', 'sender': '（未知发件人）',
                     'received': received.astimezone(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M'),
                     'size': int(size[1])})
    if rows:
        status, headers = connection.uid('FETCH', ','.join(row['uid'] for row in rows),
                                         '(UID BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')
        if status != 'OK':
            raise RuntimeError('Headers fetch failed')
        mapping = {row['uid']: row for row in rows}
        for chunk in headers:
            if isinstance(chunk, tuple):
                uid = re.search(rb'UID (\d+)', chunk[0])
                row = mapping.get(uid[1].decode('ascii')) if uid else None
                if row is not None:
                    message = email.message_from_bytes(chunk[1][:65536], policy=policy.default)
                    row.update(subject=str(message.get('Subject', '（无主题）'))[:300],
                               sender=str(message.get('From', '（未知发件人）'))[:300])
    return validity, sorted(rows, key=lambda row: int(row['uid']), reverse=True)


@contextmanager
def mailbox_lock():
    if not IMAP_LOCK.acquire(timeout=1):
        raise TimeoutError('Mailbox busy')
    try:
        yield
    finally:
        IMAP_LOCK.release()


def list_mail():
    with mailbox_lock():
        if CACHE['until'] > time.monotonic():
            return CACHE['rows']
        connection = connect()
        try:
            validity, rows = visible_rows(connection)
            CACHE.update(until=time.monotonic() + 30, rows=rows, validity=validity)
            return rows
        finally:
            connection.logout()


def get_mail(validity, uid):
    with mailbox_lock():
        connection = connect()
        try:
            current, rows = visible_rows(connection)
            row = next((row for row in rows if row['uid'] == str(uid)), None)
            if current != str(validity) or not row:
                raise Http404
            if row['size'] > MAX_BYTES:
                return row, '<p>这封邮件超过 5MB，请由邮箱所有者在 Gmail 中查看。</p>', []
            raw = fetch_literal(connection, str(uid), '(BODY.PEEK[])')
            if len(raw) > MAX_BYTES:
                return row, '<p>邮件过大，已停止展示。</p>', []
            body, attachments = parse_mail(raw)
            return row, body, attachments
        finally:
            connection.logout()


def parse_mail(raw):
    message = email.message_from_bytes(raw, policy=policy.default)
    attachments = []
    for part in message.walk():
        if part.get_filename():
            attachments.append(str(part.get_filename())[:180])
    body = message.get_body(preferencelist=('html', 'plain'))
    if body is None:
        return '<p>邮件没有可显示的文字正文。</p>', attachments
    try:
        content = body.get_content(errors='replace')
    except (LookupError, TypeError):
        content = (body.get_payload(decode=True) or b'').decode('utf-8', errors='replace')
    if not isinstance(content, str):
        content = ''
    content = content[:300000]
    if body.get_content_type() != 'text/html':
        return '<pre>' + html.escape(content) + '</pre>', attachments
    safe = nh3.clean(content,
        tags={'a', 'p', 'br', 'div', 'span', 'strong', 'b', 'em', 'i', 'u', 's',
              'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
              'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr'},
        clean_content_tags={'script', 'style', 'iframe', 'object', 'svg', 'math', 'form', 'template'},
        attributes={'a': {'href', 'title'}, 'td': {'colspan', 'rowspan'}, 'th': {'colspan', 'rowspan'}},
        url_schemes={'https', 'http'}, link_rel='nofollow noopener noreferrer', strip_comments=True,
        set_tag_attribute_values={'a': {'target': '_blank'}},
        attribute_filter=lambda tag, attr, value: None if attr == 'href' and not re.match(r'^https?://', value, re.I) else value)
    return safe or '<p>邮件没有可安全显示的文字正文。</p>', attachments


@require_GET
def inbox(request):
    rejection = denied(request)
    if rejection is not None:
        return rejection
    try:
        rows = list_mail()
        query = request.GET.get('q', '')[:100].strip()
        matches = [row for row in rows if query.casefold() in (row['subject'] + row['sender']).casefold()]
        return page(request, 'inbox.html', rows=matches, total=len(rows), query=query)
    except Exception as exc:
        logger.warning('Mailbox listing failed (%s)', type(exc).__name__)
        return page(request, 'inbox.html', error='暂时连接不上 Gmail。输入和邮件不会被修改，请稍后刷新。', status=503)


@require_GET
def detail(request, validity, uid):
    rejection = denied(request)
    if rejection is not None:
        return rejection
    try:
        row, body, attachments = get_mail(validity, uid)
        return page(request, 'detail.html', mail=row, attachments=attachments)
    except Http404:
        raise
    except Exception as exc:
        logger.warning('Message fetch failed (%s)', type(exc).__name__)
        return page(request, 'inbox.html', error='邮件暂时无法读取，请返回收件箱重试。', status=503)


@require_GET
def body(request, validity, uid):
    rejection = denied(request)
    if rejection is not None:
        return rejection
    try:
        _, content, _ = get_mail(validity, uid)
    except Http404:
        raise
    except Exception as exc:
        logger.warning('Message body failed (%s)', type(exc).__name__)
        return HttpResponse('邮件暂时无法读取，请刷新。', status=503)
    markup = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font:16px/1.85 sans-serif;color:#202e36;background:#fff;margin:24px;overflow-wrap:anywhere}pre{white-space:pre-wrap;font:inherit}table{max-width:100%;border-collapse:collapse}td,th{padding:8px;overflow-wrap:anywhere}a{color:#087e91}blockquote{border-left:3px solid #ccc;margin:1em 0;padding-left:1em}h1{font-size:1.7em}h2{font-size:1.4em}</style><body>' + content + '</body></html>'
    response = HttpResponse(markup)
    response['Referrer-Policy'] = 'no-referrer'
    response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-popups allow-popups-to-escape-sandbox"
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@require_GET
def stylesheet(request):
    return HttpResponse((BASE / 'mail.css').read_text(encoding='utf-8'), content_type='text/css')


urlpatterns = [path('shared-mail/', index), path('shared-mail/inbox/', inbox),
               path('shared-mail/logout/', logout), path('shared-mail/style.css', stylesheet),
               path('shared-mail/message/<int:validity>/<int:uid>/', detail),
               path('shared-mail/message/<int:validity>/<int:uid>/body/', body)]
application = get_wsgi_application()
