"""One-shot loopback form; transfers an authorized credential to our SSH host."""
import argparse
import html
import json
import os
import re
import secrets
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from django.contrib.auth.hashers import PBKDF2PasswordHasher

parser = argparse.ArgumentParser()
parser.add_argument('--key', required=True)
parser.add_argument('--receipt', required=True)
args = parser.parse_args()
token = secrets.token_urlsafe(32)
done = False
shared_password = secrets.token_urlsafe(18)


class Setup(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, status=200):
        raw = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != '/' + token or done:
            return self.send('Not found', 404)
        self.send('<!doctype html><meta charset="utf-8"><title>临时邮箱安全配置</title>'
                  '<style>body{font:17px/1.8 sans-serif;max-width:620px;margin:60px auto;padding:30px;background:#f7f8f5}input,button{padding:14px;margin:15px 0;font:inherit}input{width:100%;box-sizing:border-box}</style>'
                  '<h1>配置服务器收信凭据</h1><p>此页面仅在本机运行，将应用专用密码经 SSH 传到 heuesta.cn 自有服务器。不会用作访客密码。</p>'
                  '<form method="post"><label for="secret">Google 应用专用密码</label>'
                  '<input id="secret" type="password" name="secret" autocomplete="off" required maxlength="32">'
                  f'<input type="hidden" name="token" value="{token}">'
                  '<button type="submit">验证 IMAP 并安全配置</button></form>')

    def do_POST(self):
        global done
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if (done or self.path != '/' + token or self.headers.get('Origin') not in [origin, 'null']
                or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'):
            print('REQUEST_REJECTED', json.dumps({'origin': self.headers.get('Origin'),
                                                 'host': self.headers.get('Host')}), flush=True)
            return self.send('Forbidden', 403)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length < 2048:
            return self.send('Invalid input', 400)
        fields = parse_qs(self.rfile.read(length).decode())
        password = ''.join(fields.get('secret', [''])[0].split())
        if fields.get('token', [''])[0] != token or not re.fullmatch(r'[a-z]{16}', password):
            return self.send('Invalid input', 400)
        start = datetime.now(timezone.utc).replace(microsecond=0)
        end = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
        config = {'starts_at': start.isoformat(), 'expires_at': end.isoformat(),
                  'account': 'xiazhiyuan90@gmail.com', 'app_password': password,
                  'password_hash': PBKDF2PasswordHasher().encode(shared_password, secrets.token_hex(16)),
                  'session_secret': secrets.token_urlsafe(48), 'rate_db': '/data/rate.sqlite'}
        process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                                  '-o', 'ConnectTimeout=10', '-i', args.key, 'root@123.57.6.128',
                                  'python3 /opt/heuesta/shared-mail/provision_secret.py'],
                                 input=json.dumps(config).encode(), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=60)
        del config['app_password']
        password = ''
        if process.returncode:
            print('SETUP_FAILED', flush=True)
            return self.send('连接或认证未通过，尚未完成配置。请返回重试。', 502)
        receipt = Path(args.receipt)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        data = {'url': 'https://heuesta.cn/shared-mail/', 'password': shared_password,
                'starts_at': start.isoformat(), 'expires_at': end.isoformat()}
        receipt.with_suffix('.json').write_text(json.dumps(data), encoding='utf-8')
        china = __import__('datetime').timedelta(hours=8)
        receipt.write_text('# 临时共享邮箱访问说明\n\n入口：https://heuesta.cn/shared-mail/\n\n'
                           + '访客访问密码：`' + shared_password + '`\n\n'
                           + '停止访问：' + end.astimezone(timezone(china)).strftime('%Y-%m-%d %H:%M') + '（北京时间）\n\n'
                           + '仅展示启用后新收到的最近 100 封邮件；不发送、不删除、不改变已读状态。\n\n'
                           + '请只向可信使用者分享入口和访客密码，不要分享 Google 应用专用密码。\n'
                           + '服务到期自动封锁访问并停止容器；请随后在 Google 账号中撤销对应应用专用密码。\n', encoding='utf-8')
        done = True
        print('IMAP_AUTH_OK READONLY_OK SERVER_SECRET_INSTALLED RECEIPT_SAVED', flush=True)
        self.send('<meta charset="utf-8"><h1>IMAP 登录和只读收件验证成功</h1><p>密码已写入服务器受保护配置；访客访问说明已保存到本机私密文件。此页面现在可以关闭。</p>')
        threading.Timer(2, self.server.shutdown).start()


server = HTTPServer(('127.0.0.1', 0), Setup)
print(f'SETUP_URL=http://127.0.0.1:{server.server_port}/{token}', flush=True)
server.serve_forever()
