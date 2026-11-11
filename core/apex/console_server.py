"""Access-only WSGI origin for the existing APEX journal and command centre.

No development-token fallback, private payload export, remote code execution or
implicit external actions. Start under the approved host supervisor behind Access.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import threading
import time

from .kernel.access_auth import AccessVerifier
from .kernel.memory import Ledger

ASSETS=Path(__file__).parent/'kernel/console_assets'
HEADERS=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
         ('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),
         ('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
         ('Permissions-Policy','camera=(), microphone=(), geolocation=()')]


def content(root,path):
    assets={'/assets/console.css':('console.css','text/css; charset=utf-8'),
            '/assets/console.js':('console.js','text/javascript; charset=utf-8')}
    if path in assets:
        filename,kind=assets[path]
        return (ASSETS/filename).read_bytes(),kind
    if path not in {'/','/console','/reports','/status.json','/api/status','/reports.json'}:
        raise KeyError('Unknown route')
    from .kernel.dashboard import snapshot,render
    with Ledger.read_only(root) as ledger:
        data=snapshot(ledger,root=root)
    if path in {'/','/console','/reports'}:
        return render(data,path=='/reports'),'text/html; charset=utf-8'
    return json.dumps({'reports':data['reports']} if path=='/reports.json' else data,
                      ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8'


class ReloadingVerifier:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock()
        self.verifier=AccessVerifier.load(self.path)
        self.signature=self._signature()
    def _signature(self):
        s=self.path.stat();return (s.st_ino,s.st_mtime_ns,s.st_size)
    def valid(self,token):
        # An operator may atomically rotate public JWKS config without restart.
        # Missing, changed-invalid or expired configuration always fails closed.
        with self.lock:
            try:
                sig=self._signature()
                if sig!=self.signature:
                    self.verifier=AccessVerifier.load(self.path);self.signature=sig
                return self.verifier.valid(token)
            except Exception:return False


class ConsoleApp:
    def __init__(self,root,verifier):
        self.root=Path(root);self.verifier=verifier
        self.lock=threading.Lock();self.requests=deque()
    def __call__(self,environ,start_response):
        now=time.monotonic()
        with self.lock:
            while self.requests and self.requests[0]<=now-60:self.requests.popleft()
            limited=len(self.requests)>=300
            if not limited:self.requests.append(now)
        code=200;body=b'';kind='application/json; charset=utf-8'
        if limited:code=429;body=b'{"error":"RATE_LIMITED"}'
        elif not self.verifier.valid(environ.get('HTTP_CF_ACCESS_JWT_ASSERTION','')):
            code=401;body=b'{"error":"OWNER_AUTHENTICATION_REQUIRED"}'
        elif environ.get('REQUEST_METHOD') not in {'GET','HEAD'}:
            code=405;body=b'{"error":"READ_ONLY; use authenticated operator CLI for STOP"}'
        else:
            try:body,kind=content(self.root,environ.get('PATH_INFO',''))
            except KeyError:code=404;body=b'{"error":"NOT_FOUND"}'
            except Exception:code=503;body=b'{"error":"EVIDENCE_UNAVAILABLE"}'
        labels={200:'OK',401:'Unauthorized',404:'Not Found',405:'Method Not Allowed',429:'Too Many Requests',503:'Service Unavailable'}
        headers=HEADERS+[('Content-Type',kind),('Content-Length',str(len(body)))]
        if code==429:headers.append(('Retry-After','60'))
        if code==405:headers.append(('Allow','GET, HEAD'))
        start_response(str(code)+' '+labels[code],headers)
        return [b'' if environ.get('REQUEST_METHOD')=='HEAD' else body]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--access-config',type=Path,required=True)
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    if not 1024<=args.port<=65535:raise ValueError('Unprivileged loopback port required')
    # Load and verify before opening listener; no anonymous health/data path.
    app=ConsoleApp(args.root,ReloadingVerifier(args.access_config))
    from waitress import serve
    serve(app,listen='127.0.0.1:'+str(args.port),threads=4,connection_limit=32,
          channel_timeout=15,cleanup_interval=5,max_request_header_size=32768,
          max_request_body_size=1024,clear_untrusted_proxy_headers=True,
          channel_request_lookahead=0,expose_tracebacks=False,ident='APEX')


if __name__=='__main__':main()
