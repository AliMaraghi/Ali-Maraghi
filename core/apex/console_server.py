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


def connections_page(root):
    import html
    from .declared_targets import directory,COMPARTMENTS
    with Ledger.read_only(root) as ledger:
        rows=directory(ledger)
    links={'google':'/connections/google','meta':'/connections/meta'}
    live=sum(r['state'] in ('LIVE','LIVE_PUBLIC_RECEIPT') for r in rows)
    out=['<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>Connections</title><link rel="stylesheet" href="/assets/console.css"><body><main><h1>Account connections</h1>',
         '<p>'+str(len(rows))+' founder-declared targets · '+str(live)+' with a live retrieval receipt. '
         'An adapter is not a connection; LIVE requires an authorized request receipt in the Ledger. '
         'Not the authoritative 130-provider inventory (not found in repository).</p>',
         '<p><a href="/connections/finance">Financial accounts</a> · <a href="/connections/google">Google</a> · '
         '<a href="/connections/meta">Meta</a> · <a href="/console">Founder console</a></p>']
    for compartment in COMPARTMENTS:
        group=[r for r in rows if r['compartment']==compartment]
        if not group:continue
        out.append('<section><h2>'+html.escape(compartment)+('' if COMPARTMENTS[compartment]['briefing'] else ' (segregated: excluded from briefings)')+'</h2><table><tr><th>Target</th><th>Route</th><th>State</th><th>Notes</th></tr>')
        for r in group:
            link=links.get(r['adapter']) or ('/connections/finance' if (r['adapter'] or '').startswith('finance:') else None)
            name=html.escape(r['target'])
            out.append('<tr><td>'+('<a href="'+link+'">'+name+'</a>' if link else name)+'</td><td>'+r['route']+'</td><td><b>'+r['state']+'</b>'
                       +(' #'+str(r['receipt_seq']) if r['receipt_seq'] else '')+'</td><td>'+html.escape(r['note'])+(' [to verify]' if r['verify'] else '')+'</td></tr>')
        out.append('</table></section>')
    out.append('</main></body></html>')
    return ''.join(out).encode()


def content(root,path):
    assets={'/assets/console.css':('console.css','text/css; charset=utf-8'),
            '/assets/console.js':('console.js','text/javascript; charset=utf-8')}
    if path in assets:
        filename,kind=assets[path]
        return (ASSETS/filename).read_bytes(),kind
    if path=='/connections':
        return connections_page(root),'text/html; charset=utf-8'
    if path not in {'/','/console','/reports','/status.json','/api/status','/reports.json'}:
        raise KeyError('Unknown route')
    from .kernel.dashboard import snapshot,render
    with Ledger.read_only(root) as ledger:
        data=snapshot(ledger,root=root)
    if path in {'/','/console','/reports'}:
        return render(data,path=='/reports'),'text/html; charset=utf-8'
    return json.dumps({'reports':data['reports']} if path=='/reports.json' else data,
                      ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8'


from .finance_web import is_finance_path
from .finance import TARGETS as FINANCE_TARGETS
from .approvals_web import is_approvals_path
from .bridge_web import is_bridge_path

META_PATHS=frozenset({'/connections/meta','/connections/meta/sync','/auth/meta/start','/auth/meta/callback','/auth/meta/disconnect'})


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
    def __init__(self,root,verifier,google_routes=None,meta_routes=None,finance_routes=None,approval_routes=None,bridge_routes=None):
        self.root=Path(root);self.verifier=verifier;self.google_routes=google_routes;self.meta_routes=meta_routes;self.finance_routes=finance_routes
        self.approval_routes=approval_routes;self.bridge_routes=bridge_routes
        self.lock=threading.Lock();self.requests=deque()
    def __call__(self,environ,start_response):
        now=time.monotonic()
        with self.lock:
            while self.requests and self.requests[0]<=now-60:self.requests.popleft()
            limited=len(self.requests)>=300
            if not limited:self.requests.append(now)
        code=200;body=b'';kind='application/json; charset=utf-8';extra=[];form_action=None
        path_info=environ.get('PATH_INFO')
        if limited:code=429;body=b'{"error":"RATE_LIMITED"}'
        elif not self.verifier.valid(environ.get('HTTP_CF_ACCESS_JWT_ASSERTION','')):
            code=401;body=b'{"error":"OWNER_AUTHENTICATION_REQUIRED"}'
        elif not self.google_routes and path_info=='/connections/google' and environ.get('REQUEST_METHOD')=='GET':
            body=b'{"status":"BLOCKED_EXTERNAL_AUTH","required":"Protected Google client, persistent encryption key and reviewed import policy configuration"}'
        elif self.google_routes and path_info in {
                '/connections/google','/connections/google/sync','/connections/google/schedule',
                '/connections/google/unschedule','/auth/google/start',
                '/auth/google/callback','/auth/google/disconnect','/auth/logout'}:
            form_action="'self' https://accounts.google.com https://www.facebook.com"
            try:
                if isinstance(self.verifier,ReloadingVerifier) and self.verifier.verifier.owner != self.google_routes.owner:
                    raise PermissionError('Access owner configuration changed')
                code,body,extra,kind=self.google_routes.handle(environ)
            except PermissionError:code=403;body=b'{"error":"AUTHORIZATION_REQUIRED_OR_REJECTED"}'
            except (ValueError,KeyError,TypeError):code=400;body=b'{"error":"INVALID_REQUEST_OR_CONFIGURATION"}'
            except Exception:code=503;body=b'{"error":"CONNECTION_UNAVAILABLE"}'
        elif self.meta_routes and path_info in META_PATHS:
            form_action="'self' https://accounts.google.com https://www.facebook.com"
            try:
                if isinstance(self.verifier,ReloadingVerifier) and self.verifier.verifier.owner != self.meta_routes.owner:
                    raise PermissionError('Access owner configuration changed')
                code,body,extra,kind=self.meta_routes.handle(environ)
            except PermissionError:code=403;body=b'{"error":"AUTHORIZATION_REQUIRED_OR_REJECTED"}'
            except (ValueError,KeyError,TypeError):code=400;body=b'{"error":"INVALID_REQUEST_OR_CONFIGURATION"}'
            except Exception:code=503;body=b'{"error":"CONNECTION_UNAVAILABLE"}'
        elif self.finance_routes and is_finance_path(path_info):
            form_action="'self' https://accounts.google.com https://www.facebook.com"
            try:
                if isinstance(self.verifier,ReloadingVerifier) and self.verifier.verifier.owner != self.finance_routes.owner:
                    raise PermissionError('Access owner configuration changed')
                code,body,extra,kind=self.finance_routes.handle(environ)
            except PermissionError:code=403;body=b'{"error":"AUTHORIZATION_REQUIRED_OR_REJECTED"}'
            except (ValueError,KeyError,TypeError):code=400;body=b'{"error":"INVALID_REQUEST_OR_CONFIGURATION"}'
            except Exception:code=503;body=b'{"error":"CONNECTION_UNAVAILABLE"}'
        elif not self.finance_routes and path_info=='/connections/finance' and environ.get('REQUEST_METHOD')=='GET':
            body=json.dumps({'status':'BLOCKED_EXTERNAL_AUTH','required':'Protected finance configuration',
                             'targets':[{'name':t['name'],'status':'NOT_CONNECTED'} for t in FINANCE_TARGETS]}).encode()
        elif not self.meta_routes and path_info=='/connections/meta' and environ.get('REQUEST_METHOD')=='GET':
            body=b'{"status":"BLOCKED_EXTERNAL_AUTH","required":"Protected Meta app configuration"}'
        elif not self.approval_routes and is_approvals_path(path_info):
            code=503;body=b'{"error":"APPROVALS_NOT_CONFIGURED"}'
        elif self.approval_routes and is_approvals_path(path_info):
            form_action="'self'"
            try:
                code,body,extra,kind=self.approval_routes.handle(environ)
            except PermissionError:code=403;body=b'{"error":"AUTHORIZATION_REQUIRED_OR_REJECTED"}'
            except (ValueError,KeyError,TypeError):code=400;body=b'{"error":"INVALID_REQUEST_OR_CONFIGURATION"}'
            except Exception:code=503;body=b'{"error":"CONNECTION_UNAVAILABLE"}'
        elif not self.bridge_routes and is_bridge_path(path_info):
            code=503;body=b'{"error":"BRIDGE_NOT_CONFIGURED"}'
        elif self.bridge_routes and is_bridge_path(path_info):
            form_action="'self'"
            try:
                code,body,extra,kind=self.bridge_routes.handle(environ)
            except PermissionError:code=403;body=b'{"error":"AUTHORIZATION_REQUIRED_OR_REJECTED"}'
            except (ValueError,KeyError,TypeError):code=400;body=b'{"error":"INVALID_REQUEST_OR_CONFIGURATION"}'
            except Exception:code=503;body=b'{"error":"CONNECTION_UNAVAILABLE"}'
        elif environ.get('REQUEST_METHOD') not in {'GET','HEAD'}:
            code=405;body=b'{"error":"READ_ONLY; use authenticated operator CLI for STOP"}'
        else:
            try:body,kind=content(self.root,path_info or '')
            except KeyError:code=404;body=b'{"error":"NOT_FOUND"}'
            except Exception:code=503;body=b'{"error":"EVIDENCE_UNAVAILABLE"}'
        labels={200:'OK',303:'See Other',400:'Bad Request',403:'Forbidden',401:'Unauthorized',404:'Not Found',405:'Method Not Allowed',429:'Too Many Requests',503:'Service Unavailable'}
        headers=[(k,v.replace("form-action 'none'","form-action "+form_action) if form_action and k=='Content-Security-Policy' else v) for k,v in HEADERS]+extra+[('Content-Type',kind),('Content-Length',str(len(body)))]
        if code==429:headers.append(('Retry-After','60'))
        if code==405:headers.append(('Allow','GET, HEAD'))
        start_response(str(code)+' '+labels[code],headers)
        return [b'' if environ.get('REQUEST_METHOD')=='HEAD' else body]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--access-config',type=Path,required=True)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--google-config',type=Path,default=Path('/etc/apex/google-runtime.json'))
    p.add_argument('--meta-config',type=Path,default=Path('/etc/apex/meta-runtime.json'))
    p.add_argument('--finance-config',type=Path,default=Path('/etc/apex/finance-runtime.json'))
    p.add_argument('--approvals-config',type=Path,default=Path('/etc/apex/approvals-runtime.json'))
    args=p.parse_args()
    if not 1024<=args.port<=65535:raise ValueError('Unprivileged loopback port required')
    # Load and verify before opening listener; no anonymous health/data path.
    verifier=ReloadingVerifier(args.access_config)
    google=None
    if args.google_config.exists():
        from .google_web import GoogleRoutes
        google=GoogleRoutes(args.root,args.google_config,verifier.verifier.owner)
    meta=None
    if args.meta_config.exists():
        from .meta_web import MetaRoutes
        meta=MetaRoutes(args.root,args.meta_config,verifier.verifier.owner)
    finance=None
    if args.finance_config.exists():
        from .finance_web import FinanceRoutes
        finance=FinanceRoutes(args.root,args.finance_config,verifier.verifier.owner)
    approvals=None
    if args.approvals_config.exists():
        from .approvals_web import ApprovalRoutes
        approvals=ApprovalRoutes(args.root,args.approvals_config,verifier.verifier.owner)
    from .bridge_web import BridgeRoutes
    bridge=BridgeRoutes(args.root,verifier.verifier.owner)
    app=ConsoleApp(args.root,verifier,google,meta,finance,approvals,bridge)
    from waitress import serve
    serve(app,listen='127.0.0.1:'+str(args.port),threads=4,connection_limit=32,
          channel_timeout=15,cleanup_interval=5,max_request_header_size=32768,
          max_request_body_size=1024,clear_untrusted_proxy_headers=True,
          channel_request_lookahead=0,expose_tracebacks=False,ident='APEX')


if __name__=='__main__':main()
