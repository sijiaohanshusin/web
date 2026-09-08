"""Live read-only checks; no email content, cookies or passwords printed."""
import argparse
import json
import re
from pathlib import Path
import requests

parser = argparse.ArgumentParser()
parser.add_argument('--receipt', required=True)
parser.add_argument('--direct', action='store_true')
args = parser.parse_args()
receipt = json.loads(Path(args.receipt).read_text(encoding='utf-8'))
url = receipt['url']
session = requests.Session()
session.trust_env = not args.direct
anonymous_session = requests.Session()
anonymous_session.trust_env = not args.direct
initial = session.get(url, timeout=30)
assert initial.status_code == 200, ('entry', initial.status_code)
assert 'name="password"' in initial.text
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', initial.text)[1]
logged = session.post(url, data={'csrfmiddlewaretoken': token, 'password': receipt['password']},
                      headers={'Origin': 'https://heuesta.cn', 'Referer': url}, timeout=45)
assert logged.status_code == 200, ('login/inbox', logged.status_code)
assert '共享收件箱' in logged.text and 'name="password"' not in logged.text
assert 'xiazhiyuan90@gmail.com' in logged.text
assert 'no-store' in logged.headers.get('Cache-Control', '')
assert 'no-store' in logged.headers.get('CDN-Cache-Control', '')
for suffix in ['inbox/', 'message/1/1/', 'message/1/1/body/']:
    anonymous = anonymous_session.get(url + suffix, allow_redirects=False, timeout=30)
    assert anonymous.status_code == 302, ('anonymous', suffix, anonymous.status_code)
    assert anonymous.headers['Location'] == '/shared-mail/'
    assert 'no-store' in anonymous.headers.get('Cache-Control', '')
    assert 'xiazhiyuan90@gmail.com' not in anonymous.text
cookie = next(cookie for cookie in session.cookies if cookie.name == 'heuesta_shared_mail')
assert cookie.secure and cookie.path == '/shared-mail/'
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', logged.text)[1]
out = session.post(url + 'logout/', data={'csrfmiddlewaretoken': token},
                   headers={'Origin': 'https://heuesta.cn', 'Referer': url + 'inbox/'}, timeout=30)
assert out.status_code == 200 and 'name="password"' in out.text
assert session.get(url + 'inbox/', allow_redirects=False, timeout=30).status_code == 302
for endpoint in ['https://heuesta.cn/', 'https://heuesta.cn/team/', 'https://bbs.heuesta.cn/']:
    response = anonymous_session.get(endpoint, timeout=30)
    assert response.status_code == 200, ('unaffected', endpoint, response.status_code)
print(json.dumps({'https': 'ok', 'visitor_login': 'ok', 'gmail_inbox': 'ok',
                  'anonymous_after_authenticated_cdn_checks': 'ok', 'logout': 'ok',
                  'main_and_forum': 'ok', 'expires_at': receipt['expires_at'],
                  'visible_message_links': len(re.findall(r'href="/shared-mail/message/', logged.text)),
                  'cache_status': logged.headers.get('EO-Cache-Status', 'not reported')}, indent=2))
