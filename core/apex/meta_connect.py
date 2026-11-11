"""Owner-session-bound Facebook Login (read-only Pages/Instagram discovery).

State, encrypted long-lived user token and audit live in the existing Ledger.
Fixed Graph operations only; token/secret travel via subprocess stdin, never argv,
environment, logs or audit. Graph version comes from operator config, never guessed.
"""
import hashlib
import hmac
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json
from .meta_readonly import HOST, SCOPES, MetaBinding, bounded
from .sources.public_http import Connection, resolve_public, LIMIT

REDIRECT = 'https://console.apexcorelab.uk/auth/meta/callback'
TOKEN_RE = r'[A-Za-z0-9._~+/=-]+'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def graph_path(op, version, args):
    bounded(version, r'v[0-9]{1,3}\.0', 8)
    if op == 'code':
        return '/' + version + '/oauth/access_token?' + urlencode({
            'client_id': bounded(args['app_id'], r'[0-9]+', 40), 'redirect_uri': REDIRECT,
            'client_secret': bounded(args['app_secret'], r'[A-Za-z0-9]+', 128),
            'code': bounded(args['code'], r'[A-Za-z0-9_\-#.]+', 2048)}), None
    if op == 'long':
        return '/' + version + '/oauth/access_token?' + urlencode({
            'grant_type': 'fb_exchange_token', 'client_id': bounded(args['app_id'], r'[0-9]+', 40),
            'client_secret': bounded(args['app_secret'], r'[A-Za-z0-9]+', 128),
            'fb_exchange_token': bounded(args['token'], TOKEN_RE, 8192)}), None
    if op in ('permissions', 'me'):
        resource = '/me/permissions?limit=50' if op == 'permissions' else '/me?fields=id'
        return '/' + version + resource, bounded(args['token'], TOKEN_RE, 8192)
    raise ValueError('Unsupported Graph operation')


def fetch(op, version, **args):
    path, bearer = graph_path(op, version, args)
    family, address = resolve_public(HOST)
    connection = Connection(HOST, family, address)
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    try:
        connection.request('GET', path, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return {'http_status': response.status}
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('Invalid Graph response bounds')
        return {'http_status': 200, 'data': strict_json(body.decode())}
    finally:
        connection.close()


def call(op, version, **args):
    try:
        result = subprocess.run([sys.executable, '-B', '-m', 'apex.meta_connect'],
                                input=json.dumps({'op': op, 'version': version, **args}).encode(),
                                capture_output=True, timeout=20,
                                env={'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout) > 2_000_000:
            raise ValueError()
        response = strict_json(result.stdout.decode())
    except Exception:
        raise RuntimeError('Meta transport failed') from None
    if response.get('http_status') != 200 or not isinstance(response.get('data'), dict):
        raise RuntimeError('Meta request rejected: ' + str(response.get('http_status')))
    return response['data']


class MetaConnection:
    def __init__(self, ledger, key, owner, app_id, app_secret, version, privacy_review):
        self.ledger, self.cipher, self.owner = ledger, Fernet(key), owner
        self.app_id = bounded(app_id, r'[0-9]+', 40)
        self.app_secret = bounded(app_secret, r'[A-Za-z0-9]+', 128)
        self.version = bounded(version, r'v[0-9]{1,3}\.0', 8)
        self.privacy_review = bounded(privacy_review, r'[A-Za-z0-9_.-]+', 128)
        self.account = digest(owner + '\n' + self.app_id)
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS meta_authorization_pending (state_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL, expires INTEGER NOT NULL)')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS meta_credentials (account TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')

    def begin(self, authenticated_owner, session):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        bounded(session, r'[A-Za-z0-9_-]+', 256)
        now = int(time.time()); state = secrets.token_urlsafe(32)
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            self.ledger.db.execute('DELETE FROM meta_authorization_pending WHERE expires<=?', (now,))
            if self.ledger.db.execute('SELECT count(*) FROM meta_authorization_pending').fetchone()[0] >= 10:
                raise ValueError('Pending authorization cap')
            self.ledger.db.execute('INSERT INTO meta_authorization_pending VALUES(?,?,?)', (digest(state), digest(session), now + 600))
            self.ledger._append('meta-start-' + digest(state), 'decision', 'personal',
                                {'phase': 'PENDING_OWNER_CONSENT', 'scopes': sorted(SCOPES), 'expires_at': now + 600})
        return 'https://www.facebook.com/' + self.version + '/dialog/oauth?' + urlencode({
            'client_id': self.app_id, 'redirect_uri': REDIRECT, 'state': state,
            'response_type': 'code', 'scope': ','.join(sorted(SCOPES))})

    def callback(self, authenticated_owner, session, state, code, transport=call):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        bounded(state, r'[A-Za-z0-9_-]+', 256); bounded(session, r'[A-Za-z0-9_-]+', 256)
        # Consume state before any remote exchange; failures require a new consent.
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row = self.ledger.db.execute('SELECT session_hash,expires FROM meta_authorization_pending WHERE state_hash=?', (digest(state),)).fetchone()
            if row is None or row[1] <= time.time() or not hmac.compare_digest(row[0], digest(session)):
                raise PermissionError('Invalid, expired or replayed authorization state')
            self.ledger.db.execute('DELETE FROM meta_authorization_pending WHERE state_hash=?', (digest(state),))
        short = transport('code', self.version, app_id=self.app_id, app_secret=self.app_secret, code=code)
        long = transport('long', self.version, app_id=self.app_id, app_secret=self.app_secret,
                         token=bounded(short.get('access_token'), TOKEN_RE, 8192))
        token = bounded(long.get('access_token'), TOKEN_RE, 8192)
        lifetime = long.get('expires_in')
        if type(lifetime) is not int or not 3600 <= lifetime <= 86400 * 90:
            raise ValueError('Unexpected token lifetime')
        perms = transport('permissions', self.version, token=token).get('data')
        if not isinstance(perms, list) or len(perms) > 50:
            raise ValueError('Invalid permission list')
        granted = frozenset(p['permission'] for p in perms if isinstance(p, dict)
                            and p.get('status') == 'granted' and isinstance(p.get('permission'), str))
        if not SCOPES <= granted:
            raise PermissionError('Required Meta permissions were not all granted')
        user = bounded(transport('me', self.version, token=token).get('id'), r'[0-9]+', 40)
        record = {'token': token, 'expires_at': int(time.time()) + lifetime,
                  'scopes': sorted(granted & SCOPES), 'grant_reference': 'meta-' + digest(user)[:24], 'status': 'CONNECTED'}
        self._save(record, 'META_CONNECTED')
        return self.status()

    def _load(self):
        row = self.ledger.db.execute('SELECT encrypted,generation FROM meta_credentials WHERE account=?', (self.account,)).fetchone()
        return (strict_json(self.cipher.decrypt(row[0]).decode()), row[1]) if row else (None, 0)

    def _save(self, record, phase):
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            _, generation = self._load()
            self.ledger.db.execute('INSERT OR REPLACE INTO meta_credentials VALUES(?,?,?)',
                                   (self.account, self.cipher.encrypt(json.dumps(record).encode()), generation + 1))
            self.ledger._append('meta-cred-' + self.account[:16] + '-' + str(generation + 1), 'decision', 'personal',
                                {'phase': phase, 'expires_at': record.get('expires_at'), 'scopes': record.get('scopes')})

    def status(self):
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED':
            return {'status': 'AUTH_REQUIRED'}
        if record['expires_at'] <= time.time():
            return {'status': 'EXPIRED_RECONNECT_REQUIRED'}
        return {'status': 'CONNECTED', 'expires_at': record['expires_at'],
                'reconnect_within_days': int((record['expires_at'] - time.time()) // 86400)}

    def binding(self):
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED':
            raise PermissionError('AUTH_REQUIRED')
        return MetaBinding(self.owner, self.app_id, self.version, record['grant_reference'],
                           frozenset(record['scopes']), record['expires_at'], self.privacy_review)

    def token(self):
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED' or record['expires_at'] <= time.time():
            raise PermissionError('AUTH_REQUIRED')
        return record['token']

    def disconnect(self):
        self._save({'status': 'REVOKED'}, 'LOCALLY_DISCONNECTED')


if __name__ == '__main__':
    try:
        args = strict_json(sys.stdin.buffer.read(16385).decode())
        print(json.dumps(fetch(**args), allow_nan=False))
    except Exception:
        print('{"http_status":0}')
