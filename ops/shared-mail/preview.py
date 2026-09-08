"""Loopback-only visual fixture. Never connects to Gmail or uses real credentials."""
import test_service
import service
from wsgiref.simple_server import make_server, WSGIRequestHandler

service.list_mail = lambda: [
    {'uid': '1', 'validity': '5', 'subject': '欢迎使用临时共享收件箱（本地测试）',
     'sender': '演示发送者 <demo@example.test>', 'received': '09-08 19:00', 'size': 200},
    {'uid': '2', 'validity': '5', 'subject': '项目资料已准备好，请确认接收',
     'sender': '工作组 <team@example.test>', 'received': '09-08 18:50', 'size': 200}]
service.get_mail = lambda validity, uid: (
    service.list_mail()[0],
    '<h2>你好，欢迎使用共享收件箱。</h2><p>这是仅在本地运行的测试邮件，正式站没有创建演示内容。</p>'
    '<p><strong>支持中文、分段和链接。</strong></p><p>外部图片、脚本与附件下载均被屏蔽。</p>', ['示例附件.pdf'])


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def preview_app(environ, start_response):
    if environ['PATH_INFO'] == '/qa/':
        start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8'), ('Cache-Control', 'no-store')])
        return ['<!doctype html><title>手机布局验收（本地虚构内容）</title><style>body{display:flex;gap:32px;background:#dde5e5;font:14px sans-serif;margin:20px}iframe{display:block;border:1px solid #aaa;background:white}</style><section><h2>390px 手机</h2><iframe width="390" height="1000" src="/shared-mail/"></iframe></section><section><h2>320px 小屏</h2><iframe width="320" height="1000" src="/shared-mail/"></iframe></section>'.encode()]
    def headers(status, items, exc_info=None):
        items = [(key, 'SAMEORIGIN' if key.lower() == 'x-frame-options' else
                  value.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
                  if key.lower() == 'content-security-policy' else value) for key, value in items]
        return start_response(status, items, exc_info)
    return service.application(environ, headers)


server = make_server('127.0.0.1', 0, preview_app, handler_class=Quiet)
print(f'PREVIEW_URL=http://127.0.0.1:{server.server_port}/shared-mail/', flush=True)
print(f'MOBILE_QA_URL=http://127.0.0.1:{server.server_port}/qa/', flush=True)
server.serve_forever()
