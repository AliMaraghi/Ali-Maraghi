"""Session-bound PKCE/state primitives; not HTTP routes or a token broker.

Uses existing Ledger transactions/audit and caller-provided protected Fernet key.
Caller must authenticate owner session over verified HTTPS/owner Access before
calling either method. No network, tokens, client secrets or implicit consent.
"""
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode,urlsplit
from cryptography.fernet import Fernet
from .kernel.schema import strict_json
from .kernel.policy import enforce_durable_stop

SCOPES={'gmail':'https://www.googleapis.com/auth/gmail.readonly',
        # drive.file reaches only files this application itself creates (the encrypted journal backup).
        'drive':'https://www.googleapis.com/auth/drive.file'}


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def bounded(value,minimum,maximum):
    if not isinstance(value,str) or not minimum<=len(value)<=maximum or not value.isascii() or any(ord(c)<=32 for c in value):
        raise ValueError('Invalid bounded authorization input')
    return value


class OAuthState:
    def __init__(self,ledger,key,client_id,redirect_uri,owner):
        self.ledger=ledger;self.cipher=Fernet(key)
        self.client_id=bounded(client_id,1,256);self.owner=bounded(owner,3,254)
        bounded(redirect_uri,1,512);u=urlsplit(redirect_uri)
        if u.scheme!='https' or u.netloc not in {'console.apexcorelab.uk','auth.apexcorelab.uk'} or u.path!='/auth/google/callback' or u.query or u.fragment:
            raise ValueError('Exact reviewed HTTPS callback required')
        self.redirect=redirect_uri
        self.binding=digest(client_id+'\n'+redirect_uri+'\n'+owner)
        with ledger.transaction():
            ledger.db.execute('''CREATE TABLE IF NOT EXISTS google_authorization_pending (
                state_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL,
                expires INTEGER NOT NULL, encrypted BLOB NOT NULL)''')

    def begin(self,owner_session,services):
        bounded(owner_session,32,256)
        if type(services) not in (list,tuple) or list(services) not in (['gmail'],['gmail','drive']):
            raise ValueError('Only the reviewed Gmail and Gmail+backup scope profiles are supported')
        now=int(time.time());state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
        scopes=['openid','email']+[SCOPES[name] for name in services]
        encrypted=self.cipher.encrypt(__import__('json').dumps({'verifier':verifier,'binding':self.binding,'scopes':scopes}).encode())
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            self.ledger.db.execute('DELETE FROM google_authorization_pending WHERE expires<=?',(now,))
            if self.ledger.db.execute('SELECT count(*) FROM google_authorization_pending').fetchone()[0]>=10:
                raise ValueError('Pending authorization cap')
            self.ledger.db.execute('INSERT INTO google_authorization_pending VALUES(?,?,?,?)',(digest(state),digest(owner_session),now+600,encrypted))
            self.ledger._append('ga-start-'+digest(state),'decision','personal',{'phase':'PENDING_OWNER_CONSENT','scope_count':len(scopes),'expires_at':now+600})
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':self.client_id,'redirect_uri':self.redirect,
            'response_type':'code','scope':' '.join(scopes),'access_type':'offline','state':state,
            # Always ask for consent: Google returns a refresh token only with an explicit consent,
            # so a silent re-approval after a failed first attempt came back without one (seen live).
            'prompt':'consent',
            'code_challenge_method':'S256','code_challenge':challenge})

    def consume(self,state,owner_session):
        bounded(state,32,256);bounded(owner_session,32,256)
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row=self.ledger.db.execute('SELECT session_hash,expires,encrypted FROM google_authorization_pending WHERE state_hash=?',(digest(state),)).fetchone()
            if row is None or row[1]<=int(time.time()) or not hmac.compare_digest(row[0],digest(owner_session)):
                raise PermissionError('Invalid, expired or replayed authorization state')
            material=strict_json(self.cipher.decrypt(row[2]).decode())
            if material['binding']!=self.binding:raise PermissionError('Authorization configuration changed')
            self.ledger.db.execute('DELETE FROM google_authorization_pending WHERE state_hash=?',(digest(state),))
            self.ledger._append('ga-use-'+digest(state),'decision','personal',{'phase':'STATE_CONSUMED_NOT_AUTHORIZED','scope_count':len(material['scopes'])})
        return {'code_verifier':material['verifier'],'scopes':material['scopes'],'redirect_uri':self.redirect}
