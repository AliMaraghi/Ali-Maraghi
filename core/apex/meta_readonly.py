"""Bounded Facebook Page/linked Instagram discovery, not a mounted OAuth flow.

Uses the existing Ledger and pinned TLS primitive. App review, account consent,
current Graph version and credential broker must be bound before live activation.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json
from .sources.public_http import Connection, resolve_public, LIMIT

HOST = 'graph.facebook.com'
SCOPES = frozenset({'pages_show_list', 'pages_read_engagement', 'instagram_basic'})
PROVIDER = {'provider_id':'meta-pages-instagram', 'category':'social',
    'official_api':'https://graph.facebook.com',
    'developer_portal':'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/',
    'authentication':'FACEBOOK_LOGIN_USER_TOKEN',
    'capability':'bounded_managed_page_and_linked_instagram_discovery',
    'adapter_version':'1', 'implementation_state':'IMPLEMENTED_NOT_AUTHORIZED',
    'cost_limit_pence':0, 'live_verified':False}


def bounded(value, pattern, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not re.fullmatch(pattern, value):
        raise ValueError('Invalid Meta input')
    return value


@dataclass(frozen=True)
class MetaBinding:
    owner: str
    app_id: str
    version: str
    grant_reference: str
    granted_scopes: frozenset
    expires_at: int
    privacy_review: str

    def require(self):
        bounded(self.owner, r'[^\s]+', 254)
        bounded(self.app_id, r'[0-9]+', 40)
        # No guessed default: operator must bind an app-supported reviewed version.
        bounded(self.version, r'v[0-9]{1,3}\.0', 8)
        bounded(self.grant_reference, r'[A-Za-z0-9_.-]+', 128)
        bounded(self.privacy_review, r'[A-Za-z0-9_.-]+', 128)
        if type(self.granted_scopes) is not frozenset or not SCOPES <= self.granted_scopes:
            raise PermissionError('Required Meta permission grant missing')
        if type(self.expires_at) is not int or self.expires_at <= time.time():
            raise PermissionError('Meta grant expired; reconnect required')


def request_path(version, after=None):
    bounded(version, r'v[0-9]{1,3}\.0', 8)
    params = {'fields':'id,name,instagram_business_account', 'limit':20}
    if after is not None:
        params['after'] = bounded(after, r'[A-Za-z0-9_\-=/+]+', 2048)
    return '/' + version + '/me/accounts?' + urlencode(params)


def fetch(version, after, token):
    path = request_path(version, after)
    bounded(token, r'[A-Za-z0-9._~+/=-]+', 8192)
    family, address = resolve_public(HOST)
    connection = Connection(HOST, family, address)
    try:
        connection.request('GET', path, headers={'Authorization':'Bearer '+token,
            'Accept':'application/json', 'Accept-Encoding':'identity', 'Connection':'close'})
        response = connection.getresponse()
        if response.status != 200:
            return {'http_status':response.status}  # No upstream body/credentials in logs.
        length = response.getheader('Content-Length')
        if (response.getheader('Content-Encoding','identity').lower() != 'identity'
                or response.getheader('Content-Type','').split(';')[0].strip() != 'application/json'
                or (length is not None and (not length.isascii() or not length.isdecimal() or int(length)>LIMIT))):
            raise ValueError('Invalid Meta response bounds')
        body = response.read(LIMIT+1)
        if len(body)>LIMIT or (length is not None and int(length)!=len(body)):
            raise ValueError('Invalid Meta body size')
        return {'http_status':200, 'data':strict_json(body.decode())}
    finally:
        connection.close()


def normalize(data):
    if not isinstance(data, dict) or not isinstance(data.get('data'), list) or len(data['data'])>20:
        raise ValueError('Invalid managed page response')
    pages=[]; seen=set()
    for item in data['data']:
        if not isinstance(item, dict):raise ValueError('Invalid page')
        pid=bounded(item.get('id'),r'[0-9]+',40)
        name=item.get('name')
        if pid in seen or not isinstance(name,str) or len(name)>512:
            raise ValueError('Invalid page identity')
        seen.add(pid)
        page={'id':pid,'name':name}
        ig=item.get('instagram_business_account')
        if ig is not None:
            if not isinstance(ig,dict):raise ValueError('Invalid linked account')
            page['instagram_business_account_id']=bounded(ig.get('id'),r'[0-9]+',40)
        pages.append(page)  # Explicit projection discards unexpected access_token.
    paging=data.get('paging',{})
    if not isinstance(paging,dict):raise ValueError('Invalid paging')
    after=None
    if paging.get('next'):
        cursors=paging.get('cursors')
        if not isinstance(cursors,dict):raise ValueError('Missing cursor')
        after=bounded(cursors.get('after'),r'[A-Za-z0-9_\-=/+]+',2048)
    # Never fetch or persist the upstream next URL, which can contain credentials.
    return pages,after


class MetaClient:
    def __init__(self, ledger, binding, token_supplier):
        if not isinstance(binding,MetaBinding) or not callable(token_supplier):
            raise PermissionError('Approved Meta binding and credential broker required')
        binding.require()
        self.ledger,self.binding,self.token_supplier=ledger,binding,token_supplier

    def pages(self,after=None):
        self.binding.require();request_path(self.binding.version,after)
        enforce_durable_stop(self.ledger)
        try:
            result=subprocess.run([sys.executable,'-B','-m','apex.meta_readonly'],
                input=json.dumps({'version':self.binding.version,'after':after,'token':self.token_supplier()}).encode(),
                capture_output=True,timeout=20,
                env={'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'LANG':'C.UTF-8'})
            if result.returncode or len(result.stdout)>2_000_000:raise ValueError()
            response=strict_json(result.stdout.decode())
        except Exception:
            raise RuntimeError('Meta transport failed') from None
        status=response.get('http_status')
        if status!=200:raise RuntimeError('Meta HTTP request rejected: '+str(status))
        return normalize(response.get('data'))


class MetaPageSync:
    """One bounded page per call; encrypted pages/cursor and redacted audit atomic."""
    def __init__(self,ledger,key,binding):
        binding.require()
        self.ledger,self.binding,self.cipher=ledger,binding,Fernet(key)
        self.identity=hashlib.sha256((binding.owner+'\n'+binding.app_id).encode()).hexdigest()
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS meta_private_pages (identity TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')

    def load(self):
        row=self.ledger.db.execute('SELECT encrypted,generation FROM meta_private_pages WHERE identity=?',(self.identity,)).fetchone()
        if row:return strict_json(self.cipher.decrypt(row[0]).decode()),row[1]
        return {'pages':{},'after':None,'complete':False,'grant':self.binding.grant_reference},0

    def step(self,client):
        if not isinstance(client,MetaClient) or client.binding!=self.binding or client.ledger is not self.ledger:
            raise PermissionError('Mismatched Meta client binding')
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger);self.binding.require()
            state,generation=self.load()
            if state['grant']!=self.binding.grant_reference:raise PermissionError('Reconnect requires reviewed reset')
            if state['complete']:return {'state':'HISTORICAL_DISCOVERY_COMPLETE','current_health':'NOT_CHECKED'}
            pages,after=client.pages(state['after'])
            if after is not None and after==state['after']:raise ValueError('Repeated cursor')
            for page in pages:state['pages'][page['id']]=page
            if len(state['pages'])>100:raise ValueError('Pilot retention bound')
            state.update(after=after,complete=after is None,observed_at=int(time.time()))
            encoded=json.dumps(state,allow_nan=False).encode()
            if len(encoded)>131072:raise ValueError('State bound')
            self.ledger.db.execute('INSERT OR REPLACE INTO meta_private_pages VALUES(?,?,?)',(self.identity,self.cipher.encrypt(encoded),generation+1))
            receipt={'provider_id':PROVIDER['provider_id'],'state':'PAGE_SYNCHRONIZED',
                'page_count':len(pages),'total_pages':len(state['pages']),'more_pages':after is not None,
                'observed_at':state['observed_at'],'external_writes':0,'paid_api_spend_pence':0}
            self.ledger._append('meta-pages-'+self.identity[:16]+'-'+str(generation+1),'decision','personal',receipt)
            return receipt


if __name__=='__main__':
    try:
        args=strict_json(sys.stdin.buffer.read(16385).decode())
        print(json.dumps(fetch(**args),allow_nan=False))
    except Exception:
        print('{"http_status":0}')
