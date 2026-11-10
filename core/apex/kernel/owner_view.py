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
            elif self.path not in {'/', '/trace.json','/console','/reports','/status.json','/reports.json'}:
                self.send_response(404); data = b'Not found'
            else:
                try:
                    with Ledger.read_only(root) as ledger:
                        from .dashboard import snapshot, render
                        overview = snapshot(ledger)
                        result = report(ledger, trace)
                        from ..connectors import verify
                        from .jobs import Jobs
                        result['runtime']={'providers':verify(ledger),'queue':Jobs.read_only(ledger).status(),
                                           'verified_audit_events':ledger.verify()}
                        if ledger.db.execute("SELECT 1 FROM sqlite_master WHERE name='mission_graphs'").fetchone():
                            from .missions import Missions
                            result['runtime']['missions']=[Missions.read_only(ledger).status(r[0]) for r in ledger.db.execute('SELECT id FROM mission_graphs ORDER BY id')]
                    encoded = json.dumps(result, indent=2, ensure_ascii=True)
                    if self.path in {'/console','/reports'}:data=render(overview,self.path=='/reports')
                    elif self.path=='/status.json':data=json.dumps(overview).encode()
                    elif self.path=='/reports.json':data=json.dumps({'reports':overview['reports']}).encode()
                    elif self.path == '/trace.json': data = encoded.encode()
                    else:
                        data = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                            '<meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>APEX owner review</title><h1>APEX: internal research review</h1>'
                            '<p>Read-only development view. No bid, income or deployment is implied.</p>'
                            '<p>Next internal action awaits owner decision. External actions remain blocked.</p>'
                            '<pre>'+escape(encoded)+'</pre></html>').encode()
                    self.send_response(200)
                except Exception:
                    self.send_response(503); data = b'Trace unavailable'
            self.send_header('Content-Type','application/json' if self.path.endswith('.json') else 'text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
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
