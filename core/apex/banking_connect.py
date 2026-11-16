"""Owner-session-bound Open Banking consent (read-only Account Information only).

Structural scaffold, not a mounted integration: no aggregator has been chosen or
reviewed, so host and endpoint paths are operator-supplied config, never a
hardcoded or guessed default the way meta_connect.py hardcodes Facebook's real,
documented Graph API. Binding to a real provider (TrueLayer, Nordigen/GoCardless
Bank Account Data, Plaid, etc.) requires: a reviewed FCA-regulated AISP, a real
consent flow started by the owner in their own banking app, and explicit policy
review before this module's first live callback. Until then every connection
reports AUTH_REQUIRED.

Payment Initiation (moving money) is permanently out of scope for this module.
Any scope string containing 'pisp' or 'payment' is rejected before a consent URL
is ever built. State, encrypted access/refresh tokens and audit live in the
existing Ledger, same as meta_connect.py. Token/secret travel via subprocess
stdin, never argv, environment or logs.
"""
import hashlib
import hmac
import json
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json
from .sources.public_http import Connection, resolve_public, LIMIT

TOKEN_RE = r'[A-Za-z0-9._~+/=-]+'
FORBIDDEN_SCOPE = re.compile(r'pisp|payment', re.I)


def bounded(value, pattern, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not re.fullmatch(pattern, value):
        raise ValueError('Invalid banking input')
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require_read_only(scopes):
    if not isinstance(scopes, (list, tuple, frozenset, set)) or not 1 <= len(scopes) <= 10:
        raise ValueError('Invalid scope set')
    cleaned = []
    for scope in scopes:
        bounded(scope, r'[A-Za-z0-9_.:-]+', 128)
        if FORBIDDEN_SCOPE.search(scope):
            raise PermissionError('Payment-initiation scope is permanently disallowed')
        cleaned.append(scope)
    return sorted(set(cleaned))


def graph_path(op, config, args):
    if op == 'code':
        return config['token_path'], None, urlencode({
            'grant_type': 'authorization_code', 'client_id': config['client_id'],
            'client_secret': config['client_secret'], 'redirect_uri': config['redirect_uri'],
            'code': bounded(args['code'], r'[A-Za-z0-9_\-#.]+', 2048)})
    if op == 'accounts':
        return config['accounts_path'], bounded(args['token'], TOKEN_RE, 8192), None
    if op == 'transactions':
        return config['transactions_path'], bounded(args['token'], TOKEN_RE, 8192), None
    raise ValueError('Unsupported Open Banking operation')


def fetch(op, host, path, bearer, body, config):
    family, address = resolve_public(host)
    connection = Connection(host, family, address)
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
    method = 'GET'
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    if body is not None:
        method = 'POST'
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return {'http_status': response.status}
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('Invalid Open Banking response bounds')
        return {'http_status': 200, 'data': strict_json(raw.decode())}
    finally:
        connection.close()


def call(op, config, **args):
    try:
        result = subprocess.run([sys.executable, '-B', '-m', 'apex.banking_connect'],
                                input=json.dumps({'op': op, 'config': config, **args}).encode(),
                                capture_output=True, timeout=20,
                                env={'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout) > 2_000_000:
            raise ValueError()
        response = strict_json(result.stdout.decode())
    except Exception:
        raise RuntimeError('Open Banking transport failed') from None
    if response.get('http_status') != 200 or not isinstance(response.get('data'), dict):
        raise RuntimeError('Open Banking request rejected: ' + str(response.get('http_status')))
    return response['data']


class BankingConnection:
    """One owner, one aggregator config, read-only Account Information only.

    `config` must be supplied by the operator after choosing and reviewing a
    real FCA-regulated AISP: {'host', 'authorize_path', 'token_path',
    'accounts_path', 'client_id', 'client_secret', 'redirect_uri',
    'provider_id'}. Nothing here guesses or defaults a real bank/aggregator.
    """

    def __init__(self, ledger, key, owner, config, scopes):
        self.ledger, self.cipher, self.owner = ledger, Fernet(key), owner
        for field in ('host', 'authorize_path', 'token_path', 'accounts_path',
                      'client_id', 'client_secret', 'redirect_uri', 'provider_id'):
            bounded(config.get(field, ''), r'[^\s]+', 2048)
        self.config = dict(config)
        self.scopes = require_read_only(scopes)
        self.account = digest(owner + '\n' + config['provider_id'] + '\n' + config['client_id'])
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS banking_authorization_pending '
                              '(state_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL, expires INTEGER NOT NULL)')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS banking_credentials '
                              '(account TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')

    def begin(self, authenticated_owner, session):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        bounded(session, r'[A-Za-z0-9_-]+', 256)
        now = int(time.time()); state = secrets.token_urlsafe(32)
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            self.ledger.db.execute('DELETE FROM banking_authorization_pending WHERE expires<=?', (now,))
            if self.ledger.db.execute('SELECT count(*) FROM banking_authorization_pending').fetchone()[0] >= 10:
                raise ValueError('Pending authorization cap')
            self.ledger.db.execute('INSERT INTO banking_authorization_pending VALUES(?,?,?)',
                                   (digest(state), digest(session), now + 600))
            self.ledger._append('banking-start-' + digest(state), 'decision', 'personal',
                                {'phase': 'PENDING_OWNER_CONSENT', 'provider_id': self.config['provider_id'],
                                 'scopes': self.scopes, 'expires_at': now + 600})
        return 'https://' + self.config['host'] + self.config['authorize_path'] + '?' + urlencode({
            'client_id': self.config['client_id'], 'redirect_uri': self.config['redirect_uri'],
            'state': state, 'response_type': 'code', 'scope': ' '.join(self.scopes)})

    def callback(self, authenticated_owner, session, state, code, transport=call):
        if authenticated_owner != self.owner:
            raise PermissionError('Owner required')
        bounded(state, r'[A-Za-z0-9_-]+', 256); bounded(session, r'[A-Za-z0-9_-]+', 256)
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            row = self.ledger.db.execute('SELECT session_hash,expires FROM banking_authorization_pending WHERE state_hash=?',
                                         (digest(state),)).fetchone()
            if row is None or row[1] <= time.time() or not hmac.compare_digest(row[0], digest(session)):
                raise PermissionError('Invalid, expired or replayed authorization state')
            self.ledger.db.execute('DELETE FROM banking_authorization_pending WHERE state_hash=?', (digest(state),))
        tokens = transport('code', self.config, code=code)
        token = bounded(tokens.get('access_token'), TOKEN_RE, 8192)
        lifetime = tokens.get('expires_in')
        if type(lifetime) is not int or not 60 <= lifetime <= 86400 * 90:
            raise ValueError('Unexpected token lifetime')
        refresh = tokens.get('refresh_token')
        if refresh is not None:
            refresh = bounded(refresh, TOKEN_RE, 8192)
        record = {'token': token, 'refresh_token': refresh, 'expires_at': int(time.time()) + lifetime,
                  'scopes': self.scopes, 'grant_reference': 'bank-' + self.account[:24], 'status': 'CONNECTED'}
        self._save(record, 'BANKING_CONNECTED')
        return self.status()

    def _load(self):
        row = self.ledger.db.execute('SELECT encrypted,generation FROM banking_credentials WHERE account=?',
                                     (self.account,)).fetchone()
        return (strict_json(self.cipher.decrypt(row[0]).decode()), row[1]) if row else (None, 0)

    def _save(self, record, phase):
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            _, generation = self._load()
            self.ledger.db.execute('INSERT OR REPLACE INTO banking_credentials VALUES(?,?,?)',
                                   (self.account, self.cipher.encrypt(json.dumps(record).encode()), generation + 1))
            self.ledger._append('banking-cred-' + self.account[:16] + '-' + str(generation + 1), 'decision', 'personal',
                                {'phase': phase, 'expires_at': record.get('expires_at'), 'scopes': record.get('scopes')})

    def status(self):
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED':
            return {'status': 'AUTH_REQUIRED'}
        if record['expires_at'] <= time.time():
            return {'status': 'EXPIRED_RECONNECT_REQUIRED'}
        return {'status': 'CONNECTED', 'expires_at': record['expires_at'],
                'reconnect_within_days': int((record['expires_at'] - time.time()) // 86400)}

    def accounts(self, transport=call):
        """Read-only account list: id/name/currency only, never sort code/number."""
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED' or record['expires_at'] <= time.time():
            raise PermissionError('AUTH_REQUIRED')
        data = transport('accounts', self.config, token=record['token'])
        items = data.get('accounts')
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError('Invalid account list')
        accounts = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid account entry')
            accounts.append({
                'id': bounded(item.get('account_id', ''), r'[A-Za-z0-9_-]+', 128),
                'display_name': bounded(item.get('display_name', 'account'), r'.+', 256),
                'currency': bounded(item.get('currency', 'GBP'), r'[A-Z]{3}', 3),
            })  # Explicit projection: sort code / account number never leave the aggregator response.
        return accounts

    def transactions(self, transport=call):
        """Read-only recent transactions: date/description/pence only, bounded to 100 rows.
        Requires 'transactions_path' in config - optional, since it's a second capability on top
        of basic account connectivity, not required for accounts() to work."""
        record, _ = self._load()
        if not record or record.get('status') != 'CONNECTED' or record['expires_at'] <= time.time():
            raise PermissionError('AUTH_REQUIRED')
        bounded(self.config.get('transactions_path', ''), r'[^\s]+', 2048)
        data = transport('transactions', self.config, token=record['token'])
        items = data.get('transactions')
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError('Invalid transaction list')
        transactions = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid transaction entry')
            transactions.append({
                'date': bounded(item.get('date', ''), r'[0-9T:.Z+-]+', 40),
                'description': bounded(item.get('description', 'transaction'), r'.+', 300),
                'pence': int(item['pence']) if isinstance(item.get('pence'), (int, float)) else 0,
            })  # Same explicit projection discipline as accounts(): nothing else leaves the aggregator response.
        return transactions

    def disconnect(self):
        self._save({'status': 'REVOKED'}, 'LOCALLY_DISCONNECTED')


if __name__ == '__main__':
    try:
        args = strict_json(sys.stdin.buffer.read(16385).decode())
        config = args['config']
        path, bearer, body = graph_path(args['op'], config, args)
        print(json.dumps(fetch(args['op'], config['host'], path, bearer, body, config), allow_nan=False))
    except Exception:
        print('{"http_status":0}')
