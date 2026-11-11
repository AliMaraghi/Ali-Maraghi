"""Short-lived loopback-only read-only owner view. No remote/PWA deployment.

Uses an explicitly supplied ephemeral development token, never live credentials.
TLS or an authenticated private tunnel remains a separate remote-access gate.
"""
import base64
import hmac
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import time

from .memory import Ledger
from .field import report


def handler(root, trace, token, expires_at, access_verifier=None):
    if access_verifier is None and (not isinstance(token, str) or len(token) < 32 or len(token) > 128 or not token.isascii()):
        raise ValueError('A 32-128 character ephemeral development token is required')
    authorization = 'Basic '+base64.b64encode(('owner:'+token).encode()).decode() if access_verifier is None else ''

    class View(BaseHTTPRequestHandler):
        def log_message(self, *_): pass  # Never log Authorization or URLs.
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self):
            self.close_connection = True
            value = self.headers.get('Authorization', '')
            valid = (time.time() < expires_at and value.isascii()
                     and hmac.compare_digest(value, authorization))
            if access_verifier is not None:
                assertions = self.headers.get_all('Cf-Access-Jwt-Assertion', [])
                valid = len(assertions) == 1 and access_verifier.valid(assertions[0])
            if not valid:
                self.send_response(401)
                if access_verifier is None:
                    self.send_header('WWW-Authenticate','Basic realm="APEX local owner", charset="UTF-8"')
                data = b'Owner authentication required'
            elif self.path not in {'/', '/trace.json','/console','/reports','/status.json','/reports.json','/api/status','/assets/console.css','/assets/console.js'}:
                self.send_response(404); data = b'Not found'
            else:
                try:
                    if self.path != '/trace.json':
                        from ..console_server import content
                        data, content_type = content(root,self.path)
                    else:
                        with Ledger.read_only(root) as ledger:
                            result=report(ledger,trace)
                        data=json.dumps(result,ensure_ascii=True).encode()
                        content_type='application/json'
                    self.send_response(200)
                except Exception:
                    self.send_response(503); data = b'Trace unavailable'
            self.send_header('Content-Type',locals().get('content_type','text/plain; charset=utf-8'))
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_POST(self):
            self.send_error(405, 'Read-only interface')
    return View


def serve(root, trace, port=8765, access_config=None):
    if type(port) is not int or not 1024 <= port <= 65535: raise ValueError('Invalid loopback port')
    if os.geteuid() != root.stat().st_uid: raise PermissionError('Workspace owner required')
    verifier = None
    if access_config is not None:
        from .access_auth import AccessVerifier
        verifier = AccessVerifier.load(access_config)
    token = os.environ.get('APEX_LOCAL_VIEW_TOKEN') if verifier is None else None
    end = time.time()+600
    import threading
    import signal
    stopped = threading.Event()
    if verifier is not None:
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
    with HTTPServer(('127.0.0.1',port),handler(root,trace,token,end,verifier)) as server:
        server.timeout=1
        print(json.dumps({'view':'http://127.0.0.1:'+str(port), 'username':'owner',
                          'token':'SUPPLIED_IN_ENV_NOT_LOGGED', 'expires_in_seconds':600 if verifier is None else None, 'auth_mode':'CLOUDFLARE_ACCESS' if verifier else 'DEVELOPMENT_BASIC'}),flush=True)
        while not stopped.is_set() and (verifier is not None or time.time()<end):
            server.handle_request()
