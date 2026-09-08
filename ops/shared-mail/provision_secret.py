"""Root-only bootstrap: accept config on stdin, verify IMAP, never echo secrets."""
import imaplib
import json
import os
import ssl
import sys
from pathlib import Path
from gmail_transport import GmailIMAP

config = json.load(sys.stdin)
target = Path('/opt/heuesta/shared-mail/secrets/config.json')
if target.exists():
    raise SystemExit('Configuration already exists; refusing to overwrite')
if config['account'] != 'xiazhiyuan90@gmail.com':
    raise SystemExit('Unexpected account')
try:
    stage = 'connect'
    client = GmailIMAP('imap.gmail.com', 993, timeout=10,
                             ssl_context=ssl.create_default_context())
    try:
        stage = 'login'
        client.login(config['account'], config['app_password'])
        stage = 'readonly_select'
        result, _ = client.select('INBOX', readonly=True)
        if result != 'OK':
            raise RuntimeError('Read-only select failed')
    finally:
        client.logout()
except Exception as exc:
    Path('/opt/heuesta/shared-mail/setup-status.json').write_text(json.dumps({
        'stage': stage, 'error_class': type(exc).__name__,
        'authentication_failed': 'AUTHENTICATIONFAILED' in str(exc),
        'application_password_required': 'Application-specific' in str(exc),
    }))
    raise SystemExit('IMAP verification failed: ' + type(exc).__name__)
target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(target.parent, 0o700)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as file:
    json.dump(config, file)
os.chown(target, 1000, 1000)
Path('/opt/heuesta/shared-mail/setup-status.json').write_text(json.dumps({'stage': 'complete'}))
print('IMAP_AUTH_OK READONLY_OK CONFIG_INSTALLED')
