"""Local gzip lab proxy; GET-only, no production data or credentials.

Use with check_launch_quality.py --base-url http://127.0.0.1:8886.
This approximates transfer compression, not the production CDN or HTTP/2.
"""
import gzip
import threading
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
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass  # Test context/navigation can close an in-flight optional asset.

    def log_message(self, *args):
        pass


class CompressedServer:
    def __enter__(self):
        self.dev = DevServer(8885).__enter__()
        self.server = ThreadingHTTPServer(('127.0.0.1', 8886), Proxy)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.dev.__exit__(*args)


if __name__ == '__main__':
    with CompressedServer() as preview:
        print('GET-only gzip lab preview: http://127.0.0.1:8886', flush=True)
        preview.thread.join()
