"""Serves the built dashboard (apex-ui/dist) on port 8081 and forwards /api/* to the backend.

Same-origin on purpose: the dashboard and its API now share one address, so a single Cloudflare
Access sign-in on ui.apexcorelab.uk protects both, and the separate public API hostname can be
closed. The forwarder is fixed to the local backend (127.0.0.1:8000) and to paths starting
/api/ - it cannot be pointed anywhere else by a request.
"""
import http.client
import http.server
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "apex-ui" / "dist"
BACKEND_HOST, BACKEND_PORT = "127.0.0.1", int(os.environ.get("APEX_BACKEND_PORT", "8000"))
PORT = int(os.environ.get("APEX_UI_PORT", "8081"))
BIND = os.environ.get("APEX_UI_BIND", "")
MAX_BODY = 12 * 1024 * 1024          # statement uploads; the backend applies its own limits too
TIMEOUT = 330                         # the local model can take minutes to answer
FORWARD_REQUEST = ("content-type", "accept", "accept-language", "cf-access-authenticated-user-email")
FORWARD_RESPONSE = ("content-type", "allow", "cache-control")


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Permissions-Policy", "camera=(self), microphone=(self)")
        super().end_headers()

    def _plain(self, status, text):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api(self):
        if not self.path.startswith("/api/") or ".." in self.path or "\r" in self.path or "\n" in self.path:
            return self._plain(404, "not found")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._plain(400, "bad length")
        if length < 0 or length > MAX_BODY:
            return self._plain(413, "too large")
        body = self.rfile.read(length) if length else None
        headers = {k: self.headers[k] for k in self.headers if k.lower() in FORWARD_REQUEST}
        conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=TIMEOUT)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            upstream = conn.getresponse()
            data = upstream.read()
        except OSError:
            return self._plain(502, "backend unavailable")
        finally:
            conn.close()
        self.send_response(upstream.status)
        for name in FORWARD_RESPONSE:
            value = upstream.getheader(name)
            if value:
                self.send_header(name, value)
        if not upstream.getheader("cache-control"):
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        return self._api() if self.path.startswith("/api/") else super().do_GET()

    def do_HEAD(self):
        return self._plain(405, "") if self.path.startswith("/api/") else super().do_HEAD()

    def do_POST(self):
        return self._api()

    def log_message(self, *args):       # paths can carry nothing private, but keep the journal quiet
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
