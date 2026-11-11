"""Encrypted single-Ledger credentials; authorized callbacks must verify identity.

No HTTP routes or implicit consent. A refresh callback must use the reviewed token
endpoint, bounded transport, and return Google's token response. Remote refresh
cannot be rolled back; local ciphertext/generation/audit commit atomically.
"""
import hashlib
import json
import re
import time
from cryptography.fernet import Fernet
from .google_oauth_state import SCOPES, bounded
from .google_policy import ImportPolicy
from .kernel.policy import enforce_durable_stop


def secret(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', value):
        raise ValueError('Invalid credential value')
    return value


class TokenBroker:
    def __init__(self, ledger, key, owner, client_id, policy):
        bounded(owner, 3, 254); bounded(client_id, 1, 256)
        if not isinstance(policy, ImportPolicy): raise PermissionError('Import review required')
        policy.require(owner, 'gmail')
        self.ledger, self.cipher, self.owner, self.policy = ledger, Fernet(key), owner, policy
        self.client_id = client_id
        self.binding = hashlib.sha256((owner+'\n'+client_id).encode()).hexdigest()
        with ledger.transaction():
            ledger.db.execute('CREATE TABLE IF NOT EXISTS google_private_tokens (binding TEXT PRIMARY KEY, encrypted BLOB NOT NULL, generation INTEGER NOT NULL)')

    def _load(self):
        row = self.ledger.db.execute('SELECT encrypted,generation FROM google_private_tokens WHERE binding=?', (self.binding,)).fetchone()
        return (json.loads(self.cipher.decrypt(row[0])), row[1]) if row else (None, 0)

    def _save(self, data, generation, phase):
        self.ledger.db.execute('INSERT OR REPLACE INTO google_private_tokens VALUES(?,?,?)',
            (self.binding, self.cipher.encrypt(json.dumps(data, allow_nan=False).encode()), generation+1))
        self.ledger._append('google-token-'+self.binding+'-'+str(generation+1), 'decision', 'personal',
            {'phase':phase, 'generation':generation+1, 'expires_at':data.get('expires_at'), 'secrets_redacted':True})

    def _normalized(self, response, previous=None):
        if not isinstance(response, dict) or response.get('token_type') != 'Bearer':
            raise ValueError('Invalid token response')
        lifetime = response.get('expires_in')
        if type(lifetime) is not int or not 60 <= lifetime <= 86400:
            raise ValueError('Invalid token lifetime')
        scope = response.get('scope', previous.get('scope') if previous else None)
        allowed = {'openid', 'email', 'https://www.googleapis.com/auth/userinfo.email', SCOPES['gmail']}
        if not isinstance(scope, str) or SCOPES['gmail'] not in scope.split() or set(scope.split()) - allowed:
            raise PermissionError('Unexpected or missing granted scopes')
        refresh = response.get('refresh_token', previous.get('refresh_token') if previous else None)
        return {'access_token':secret(response.get('access_token')), 'refresh_token':secret(refresh),
                'scope':scope, 'expires_at':int(time.time())+lifetime, 'status':'AUTHORIZED_NOT_VERIFIED'}

    def install(self, response, verified_owner):
        """Only after callback verifies Google identity, state and owner session."""
        if verified_owner != self.owner: raise PermissionError('Google account mismatch')
        self.policy.require(self.owner, 'gmail')
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            _, generation = self._load()
            self._save(self._normalized(response), generation, 'CREDENTIAL_INSTALLED')

    def access_token(self, refresh=None):
        self.policy.require(self.owner, 'gmail')
        with self.ledger.transaction():
            enforce_durable_stop(self.ledger)
            current, generation = self._load()
            if not current or current.get('status') == 'REVOKED': raise PermissionError('AUTH_REQUIRED')
            if current['expires_at'] <= time.time()+60:
                if not callable(refresh): raise PermissionError('REFRESH_REQUIRED')
                try:
                    response = refresh(current['refresh_token'])
                except Exception:
                    raise PermissionError('REFRESH_FAILED_RECONNECT_MAY_BE_REQUIRED') from None
                current = self._normalized(response, current)
                self._save(current, generation, 'CREDENTIAL_REFRESHED')
            return current['access_token']

    def disconnect(self):
        """Local revocation only; does not claim Google-side grant revocation."""
        with self.ledger.transaction():
            _, generation = self._load()
            self._save({'status':'REVOKED'}, generation, 'LOCALLY_DISCONNECTED')

    def status(self):
        data, generation = self._load()
        if not data or data.get('status') == 'REVOKED': return {'status':'AUTH_REQUIRED'}
        return {'status':'REFRESH_REQUIRED' if data['expires_at'] <= time.time()+60 else 'AUTHORIZED_NOT_VERIFIED',
                'expires_at':data['expires_at'], 'generation':generation}
