"""Local gzip lab proxy; GET-only, no production data or credentials.

Use with check_launch_quality.py --base-url http://127.0.0.1:8886.
This approximates transfer compression, not the production CDN or HTTP/2.
"""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
from shoot import DevServer


class Proxy(BaseHTTPRequestHandler):
    def do_GET(self):
        response = requests.get('http://127.0.0.1:8885' + self.path, timeout=30,
                                headers={'Accept-Encoding': 'identity'})
        body = response.content
        mime = response.headers.get('Content-Type', '')
        compressed = any(x in mime for x in ('text/', 'javascript', 'json', 'svg', 'xml'))
        if compressed:
            body = gzip.compress(body)
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            if key.lower() not in ('content-length', 'connection', 'content-encoding', 'cache-control'):
                self.send_header(key, value)
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Cache-Control', 'max-age=3600' if self.path.startswith('/static/') else 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    with DevServer(8885), ThreadingHTTPServer(('127.0.0.1', 8886), Proxy) as server:
        print('GET-only gzip lab preview: http://127.0.0.1:8886', flush=True)
        server.serve_forever()
