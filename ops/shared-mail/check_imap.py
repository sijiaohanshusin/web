"""Read-only diagnostic, never prints mail, passwords or server response text."""
import json
import ssl
import time
from pathlib import Path
from gmail_transport import GmailIMAP, addresses

config = json.loads(Path('/run/secrets/shared-mail.json').read_text())
start = time.monotonic()
stage = 'dns'
try:
    print('DNS', addresses(), flush=True)
    stage = 'connect'
    client = GmailIMAP('imap.gmail.com', 993, timeout=8, ssl_context=ssl.create_default_context())
    print('CONNECTED', round(time.monotonic() - start, 2), flush=True)
    stage = 'auth'
    client.login(config['account'], config['app_password'])
    print('AUTHENTICATED', round(time.monotonic() - start, 2), flush=True)
    stage = 'readonly'
    client.select('INBOX', readonly=True)
    print('READONLY_OK', round(time.monotonic() - start, 2), flush=True)
    stage = 'logout'
    client.logout()
except Exception as exc:
    print('FAILED', stage, type(exc).__name__, round(time.monotonic() - start, 2), flush=True)
