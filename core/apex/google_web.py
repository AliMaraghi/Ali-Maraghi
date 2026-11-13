"""Optional owner-only Google routes mounted by the existing production console.

All calls must first pass ConsoleApp's Access verifier. Config/key are provisioned
by the administrator; missing config leaves these routes disabled. No key creation.
"""
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import secrets
import stat
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from cryptography.fernet import Fernet
from .kernel.memory import Ledger
from .kernel.schema import strict_json
from .google_policy import ImportPolicy
from .google_oauth_state import OAuthState
from .google_tokens import TokenBroker
from .google_connect import GoogleConnection
from .gmail_sync import GmailSync
from .kernel.schedules import Schedules

ORIGIN='https://console.apexcorelab.uk'
COOKIE='__Host-apex-owner'


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def protected_json(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_mode&0o077 or st.st_uid not in {0,os.geteuid()} or st.st_size>16384:
            raise PermissionError('Private regular configuration required')
        with os.fdopen(fd,'r',closefd=False) as stream:return strict_json(stream.read(16385))
    finally:os.close(fd)


def load_config(path,access_owner):
    cfg=protected_json(path)
    if cfg.get('owner')!=access_owner or cfg.get('redirect_uri')!=ORIGIN+'/auth/google/callback':
        raise PermissionError('Google and Access owner/redirect mismatch')
    Fernet(cfg['encryption_key'].encode())
    policy=ImportPolicy(cfg['owner'],frozenset({'gmail'}),cfg['review_reference'],cfg['retention_days'],cfg.get('mixed_content_reviewed'))
    policy.require(cfg['owner'],'gmail')
    return cfg


def components(ledger,cfg):
    policy=ImportPolicy(cfg['owner'],frozenset({'gmail'}),cfg['review_reference'],cfg['retention_days'],cfg['mixed_content_reviewed'])
    broker=TokenBroker(ledger,cfg['encryption_key'].encode(),cfg['owner'],cfg['client_id'],policy)
    state=OAuthState(ledger,cfg['encryption_key'].encode(),cfg['client_id'],cfg['redirect_uri'],cfg['owner'])
    return policy,broker,GoogleConnection(state,broker,cfg['client_secret'])


def scheduled_gmail_sync(ledger,path,owner_digest):
    """Worker handler: one bounded page for the owner who armed the schedule.

    Uses only the administrator-provisioned config and the encrypted token already
    installed via owner consent. Never starts consent; refresh failures surface.
    """
    cfg=protected_json(path)
    if not hmac.compare_digest(digest(cfg.get('owner','')),owner_digest):
        raise PermissionError('Scheduled owner does not match configured owner')
    load_config(path,cfg['owner'])
    policy,broker,connection=components(ledger,cfg)
    if broker.status()['status']=='AUTH_REQUIRED':raise PermissionError('Google not connected')
    return GmailSync(ledger,cfg['encryption_key'].encode(),cfg['owner'],policy).step(connection.client())


SESSION_ENTRY=frozenset({'/connections/google','/connections/meta','/connections/finance'})


def owner_session(ledger,environ,path,method):
    """Access-token-bound owner session; caller has already verified Access JWT."""
    token=environ.get('HTTP_CF_ACCESS_JWT_ASSERTION','')
    # Verified Access token binding prevents cookie reuse with a different session.
    binding=digest(token)
    cookies=SimpleCookie();cookies.load(environ.get('HTTP_COOKIE',''))
    sid=cookies[COOKIE].value if COOKIE in cookies else ''
    if len(sid)>256:raise PermissionError('Invalid session')
    now=int(time.time());headers=[]
    with ledger.transaction():
        ledger.db.execute('CREATE TABLE IF NOT EXISTS owner_web_sessions (id TEXT PRIMARY KEY, binding TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL)')
        ledger.db.execute('DELETE FROM owner_web_sessions WHERE expires<=?',(now,))
        row=ledger.db.execute('SELECT binding,csrf,expires FROM owner_web_sessions WHERE id=?',(digest(sid),)).fetchone() if sid else None
        if row and not hmac.compare_digest(row[0],binding):row=None
        if not row:
            if not (path in SESSION_ENTRY or path.startswith('/approvals') or path=='/bridge') or method!='GET':raise PermissionError('Owner session required')
            if ledger.db.execute('SELECT count(*) FROM owner_web_sessions').fetchone()[0]>=20:raise PermissionError('Session cap')
            sid=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            ledger.db.execute('INSERT INTO owner_web_sessions VALUES(?,?,?,?)',(digest(sid),binding,csrf,now+900))
            ledger._append('owner-session-'+digest(sid),'decision','personal',{'phase':'OWNER_SESSION_CREATED','expires_at':now+900})
            row=(binding,csrf,now+900)
            headers.append(('Set-Cookie',COOKIE+'='+sid+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900'))
    return sid,row,headers


def require_csrf(environ,row):
    if environ.get('HTTP_ORIGIN')!=ORIGIN or environ.get('CONTENT_TYPE')!='application/x-www-form-urlencoded':raise PermissionError('Same-origin form required')
    length=environ.get('CONTENT_LENGTH','')
    if not length.isdecimal() or not 1<=int(length)<=1024:raise ValueError('Bounded form required')
    raw=environ['wsgi.input'].read(int(length))
    if len(raw)!=int(length):raise ValueError('Incomplete form')
    form=parse_qs(raw.decode(),strict_parsing=True,max_num_fields=2)
    if set(form)!={'csrf'} or len(form['csrf'])!=1 or not hmac.compare_digest(form['csrf'][0],row[1]):raise PermissionError('CSRF rejected')


class GoogleRoutes:
    def __init__(self,root,path,owner):
        self.root,self.path,self.owner=root,path,owner
        load_config(path,owner)  # Fail startup if explicitly configured but invalid.

    def handle(self,environ):
        cfg=load_config(self.path,self.owner)
        if environ.get('HTTP_HOST')!='console.apexcorelab.uk':raise PermissionError('Exact origin required')
        method=environ.get('REQUEST_METHOD');path=environ.get('PATH_INFO')
        if method not in {'GET','POST'}:return 405,b'{"error":"METHOD_NOT_ALLOWED"}',[],'application/json'
        now=int(time.time())
        with Ledger(self.root) as ledger:
            sid,row,headers=owner_session(ledger,environ,path,method)
            policy,broker,connection=components(ledger,cfg)
            if method=='POST':
                require_csrf(environ,row)
                if path=='/auth/google/start':
                    location=connection.begin(self.owner,sid)
                    return 303,b'',headers+[('Location',location)],'text/plain'
                if path=='/auth/google/disconnect':broker.disconnect()
                elif path=='/auth/logout':
                    with ledger.transaction():
                        ledger.db.execute('DELETE FROM owner_web_sessions WHERE id=?',(digest(sid),))
                        ledger._append('owner-logout-'+digest(sid),'decision','personal',{'phase':'APPLICATION_SESSION_ENDED','upstream_access_logout':False})
                    headers.append(('Set-Cookie',COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0'))
                elif path=='/connections/google/sync':
                    receipt=GmailSync(ledger,cfg['encryption_key'].encode(),self.owner,policy).step(connection.client())
                    return 200,json.dumps(receipt).encode(),headers,'application/json'
                elif path=='/connections/google/schedule':
                    if broker.status()['status']=='AUTH_REQUIRED':raise PermissionError('Connect Google first')
                    Schedules(ledger).arm_connector('gmail',digest(self.owner),900,now,672)
                elif path=='/connections/google/unschedule':
                    Schedules(ledger).disarm_connector('gmail')
                else:return 404,b'{}',headers,'application/json'
                return 303,b'',headers+[('Location','/connections/google')],'text/plain'
            if path=='/auth/google/callback':
                query=environ.get('QUERY_STRING','')
                if len(query)>8192:raise ValueError('Callback too large')
                fields=parse_qs(query,strict_parsing=True,max_num_fields=10)
                if 'error' in fields:raise PermissionError('Consent not completed')
                if any(len(fields.get(k,[]))!=1 for k in ('state','code')):raise ValueError('Invalid callback')
                connection.callback(self.owner,sid,fields['state'][0],fields['code'][0])
                return 303,b'',headers+[('Location','/connections/google')],'text/plain'
            if path!='/connections/google':return 405,b'{}',headers,'application/json'
            status=broker.status()['status']
            recurring=next((r for r in Schedules(ledger).connector_status() if r['connector']=='gmail'),None)
            recurring='Recurring sync: not armed' if recurring is None else ('Recurring sync: '+('enabled' if recurring['enabled'] else 'disabled')+', remaining runs '+str(recurring['remaining'])+', consecutive failures '+str(recurring['failures']))
            controls=''.join('<form method="post" action="'+route+'"><input type="hidden" name="csrf" value="'+html.escape(row[1])+'"><button>'+label+'</button></form>' for route,label in [('/auth/google/start','Connect / reconnect Google'),('/connections/google/sync','Sync one bounded metadata page'),('/connections/google/schedule','Enable recurring sync (15 min, 7 days)'),('/connections/google/unschedule','Disable recurring sync'),('/auth/google/disconnect','Disconnect locally'),('/auth/logout','End application session')])
            page='<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Google connection</title><body><main><h1>Google connection</h1><p>'+html.escape(status)+'</p><p>'+html.escape(recurring)+' (runs only when the supervised worker has Google configuration).</p><p>Metadata only. Local disconnect does not revoke the Google grant. A bounded page is not a full mailbox backfill.</p>'+controls+'<a href="/console">Founder console</a></main></body></html>'
            return 200,page.encode(),headers,'text/html; charset=utf-8'
