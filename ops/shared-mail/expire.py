"""Root timer: replace only our route with 410, then stop the isolated service."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

config = json.loads(Path('/opt/heuesta/shared-mail/secrets/config.json').read_text())
if datetime.now(timezone.utc) < datetime.fromisoformat(config['expires_at']):
    raise SystemExit('Not yet expired')
snippet = Path('/etc/nginx/snippets/heuesta-shared-mail.conf')
previous = snippet.read_text()
snippet.write_text('''location = /shared-mail { return 302 /shared-mail/; }
location ^~ /shared-mail/ {
    default_type "text/html; charset=utf-8";
    add_header Cache-Control "private, no-store" always;
    add_header CDN-Cache-Control "no-store" always;
    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
    return 410 '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>临时邮箱已到期</title><body><h1>临时共享收件箱已停止服务</h1><p>一个月使用期已结束，邮件不再提供访问。请联系分享者。</p></body></html>';
}
''')
if subprocess.run(['nginx', '-t'], capture_output=True).returncode:
    snippet.write_text(previous)
    raise SystemExit('Nginx validation failed; application expiry remains enforced')
subprocess.run(['nginx', '-s', 'reload'], check=True)
subprocess.run(['docker', 'stop', 'heuesta-shared-mail'], check=True)
