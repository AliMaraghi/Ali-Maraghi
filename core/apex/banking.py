"""TrueLayer Data v3 bounded bank reads. Not proof of eligibility or consent.

No payment routes, automatic retries, fabricated PSU IP or credentials. The
operator must supply a reviewed zero-cost contract and an authorized token broker.
"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
from cryptography.fernet import Fernet
from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json, identifier
from .sources.public_http import Connection, resolve_public, LIMIT

HOST = 'api.truelayer.com'


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds()!=0: raise ValueError('UTC required')
    return parsed


def contract(operation, account=None, request_id=None, start=None, end=None, cursor=None):
    if operation == 'accounts': return 'GET','/v3/connected-accounts',None
    if not isinstance(account,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',account): raise ValueError('Invalid account')
    root='/v3/connected-accounts/'+account
    if operation=='balance': return 'GET',root+'/balance',None
    if operation=='transactions_poll': return 'GET',root+'/transactions/requests/'+str(uuid.UUID(request_id)),None
    if operation!='transactions_start': raise ValueError('Unsupported read capability')
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last or (last-first).days>31: raise ValueError('Bounded date window required')
    body={'from':first.isoformat(),'to':last.isoformat(),'page_size':50}
    if cursor is not None:
        if not isinstance(cursor,str) or not 1<=len(cursor)<=4096 or any(ord(c)<33 or ord(c)>126 for c in cursor): raise ValueError('Invalid cursor')
        body['cursor']=cursor
    return 'POST',root+'/transactions/requests',body


def consent_body(name,email,return_uri):
    if return_uri!='https://console.apexcorelab.uk/auth/banking/callback': raise ValueError('Registered HTTPS callback required')
    if (not isinstance(name,str) or not 1<=len(name)<=100 or not isinstance(email,str)
        or not 3<=len(email)<=254 or '@' not in email or any(ord(c)<32 for c in name+email)):
        raise ValueError('Explicit owner details required')
    return {'provider_selection':{'type':'user_selected','filter':{'countries':['GB'],'release_channel':'public','customer_segments':['retail']}},
        'hosted_page':{'type':'authorization_flow','redirect':{'return_uri':return_uri}},
        'scopes':['accounts','balance','transactions'],'user':{'name':name,'email':email},
        'user_consent':{'type':'authorization_flow_captured'},'data_access_type':'recurring'}


def fetch(operation,connection_id,token,**parameters):
    method,path,body=contract(operation,**parameters)
    connection_id=str(uuid.UUID(connection_id))
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}',token): raise ValueError('Invalid token')
    family,address=resolve_public(HOST); conn=Connection(HOST,family,address)
    try:
        headers={'Authorization':'Bearer '+token,'Connection-Id':connection_id,'Accept':'application/json','Accept-Encoding':'identity','Connection':'close'}
        encoded=None
        if body is not None: encoded=json.dumps(body).encode(); headers['Content-Type']='application/json'
        conn.request(method,path,encoded,headers); response=conn.getresponse()
        if response.status not in {200,202}: return {'status':response.status}
        length=response.getheader('Content-Length')
        if (response.getheader('Content-Encoding','identity').lower()!='identity'
            or response.getheader('Content-Type','').split(';')[0].strip()!='application/json'
            or (length is not None and (not length.isascii() or not length.isdecimal() or int(length)>LIMIT))): raise ValueError('Invalid bounded response')
        raw=response.read(LIMIT+1)
        if len(raw)>LIMIT or (length is not None and len(raw)!=int(length)): raise ValueError('Response bound')
        data=strict_json(raw.decode())
        if not isinstance(data,dict): raise ValueError('Invalid object')
        return {'status':response.status,'data':data}
    finally: conn.close()


class BankingClient:
    """Encrypted same-Ledger receipts; ambiguous requests require manual review.

    permission is operator-reviewed metadata, not a substitute for bank consent.
    Supplier must return access_token, expires_at, scope=data from a secure broker.
    """
    def __init__(self,ledger,key,permission,token_supplier):
        self.ledger,self.cipher,self.permission,self.token_supplier=ledger,Fernet(key),dict(permission),token_supplier
        self._require()
        self.subject=hashlib.sha256((permission['owner']+'\0'+permission['connection_id']).encode()).hexdigest()
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS banking_private_receipts (subject TEXT NOT NULL, request_key TEXT NOT NULL, encrypted BLOB NOT NULL, PRIMARY KEY(subject,request_key))')

    def _require(self):
        p=self.permission
        if (not callable(self.token_supplier) or not isinstance(p.get('owner'),str) or not p['owner']
            or type(p.get('request_cost_pence')) is not int or p['request_cost_pence']!=0
            or p.get('reviewed') is not True or p.get('scopes')!=['accounts','balance','transactions']): raise PermissionError('Reviewed zero-cost bank permission required')
        for field in ('review_reference','contract_reference'): identifier(p[field])
        uuid.UUID(p['connection_id'])
        if utc(p['consent_expires_at'])<=datetime.now(timezone.utc): raise PermissionError('Consent expired; reconnect required')

    def request(self,request_key,operation,**parameters):
        identifier(request_key)
        if len(request_key)>60: raise ValueError('Request key too long')
        contract(operation,**parameters); self._require()
        key='bank-'+self.subject[:16]+'-'+request_key
        digest=hashlib.sha256(json.dumps([operation,parameters],sort_keys=True).encode()).hexdigest()
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row=self.ledger.db.execute('SELECT encrypted FROM banking_private_receipts WHERE subject=? AND request_key=?',(self.subject,request_key)).fetchone()
            if row:
                saved=strict_json(self.cipher.decrypt(row[0]).decode())
                if saved['request_digest']!=digest: raise ValueError('Request key conflict')
                return saved
            if self.ledger.db.execute('SELECT 1 FROM events WHERE event_key=?',(key+'-intent',)).fetchone(): raise RuntimeError('AMBIGUOUS_PRIOR_ATTEMPT_REQUIRES_REVIEW')
            self.ledger._append(key+'-intent','decision','personal',{'provider':'truelayer-data-v3','operation':operation,'request_digest':digest,'state':'REQUEST_RESERVED','paid_cost_pence':0})
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger); self._require(); token=self.token_supplier()
            if token.get('scope')!='data' or utc(token['expires_at'])<=datetime.now(timezone.utc): raise PermissionError('Valid Data client token required')
            try:
                proc=subprocess.run([sys.executable,'-B','-m','apex.banking'],input=json.dumps({'operation':operation,'parameters':parameters,'connection_id':self.permission['connection_id'],'token':token['access_token']}).encode(),capture_output=True,timeout=20,env={'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'LANG':'C.UTF-8'})
                if proc.returncode or len(proc.stdout)>2_000_000: raise ValueError('Transport failure')
                reply=strict_json(proc.stdout.decode())
            except Exception: reply={'status':0}
            status=reply.get('status',0)
            if type(status) is not int: raise ValueError('Invalid status')
            saved={'request_digest':digest,'observed_at':datetime.now(timezone.utc).isoformat(),'http_status':status,'data':reply.get('data'),'operation':operation,'state':'RECEIVED_UNVALIDATED' if status in {200,202} else 'FAILED'}
            self.ledger.db.execute('INSERT INTO banking_private_receipts VALUES(?,?,?)',(self.subject,request_key,self.cipher.encrypt(json.dumps(saved,allow_nan=False).encode())))
            self.ledger._append(key+'-result','decision','personal',{'provider':'truelayer-data-v3','operation':operation,'http_status':status,'state':saved['state'],'observed_at':saved['observed_at'],'paid_cost_pence':0,'private_payload':'ENCRYPTED'})
            return saved


if __name__=='__main__':
    try:
        args=strict_json(sys.stdin.buffer.read(16385).decode())
        print(json.dumps(fetch(args['operation'],args['connection_id'],args['token'],**args['parameters']),allow_nan=False))
    except Exception: print('{"status":0}')
