"""Origin Access verification from an administrator-reviewed public JWKS snapshot.

No token-supplied URLs are fetched. Snapshot expiry fails closed; refresh requires
an authenticated operator to retrieve the team's official Access certificates.
This does not configure the upstream Access policy or prove a live deployment.
"""
import json
import math
import re
import time
from pathlib import Path


class AccessVerifier:
    def __init__(self, config):
        import jwt
        self.jwt = jwt
        self.issuer = config['issuer']
        self.audience = config['audience']
        self.owner = config['owner_email']
        if not isinstance(self.issuer, str) or not re.fullmatch(
                r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com', self.issuer):
            raise ValueError('Exact Cloudflare Access team issuer required')
        if not isinstance(self.audience, str) or not re.fullmatch(r'[a-f0-9]{64}', self.audience):
            raise ValueError('Application audience required')
        if not isinstance(self.owner, str) or not re.fullmatch(r'[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+', self.owner):
            raise ValueError('One exact owner email required')
        self.observed = config['retrieved_at']
        self.expires = config['expires_at']
        if any(type(v) is not int for v in (self.observed, self.expires)) or not (
                0 < self.observed <= time.time() < self.expires <= self.observed + 86400):
            raise ValueError('Fresh bounded key snapshot required')
        if config['source_url'] != self.issuer + '/cdn-cgi/access/certs':
            raise ValueError('Key provenance mismatch')
        keys = config['jwks']['keys']
        if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
            raise ValueError('Bounded JWKS required')
        self.keys = {}
        for key in keys:
            kid = key.get('kid')
            if not isinstance(kid,str) or not 1 <= len(kid) <= 128 or kid in self.keys:
                raise ValueError('Distinct key identifiers required')
            if key.get('kty') != 'RSA' or key.get('alg') != 'RS256' or key.get('use') != 'sig' or 'd' in key:
                raise ValueError('Public RS256 signing keys required')
            parsed = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
            if not 2048 <= parsed.key_size <= 4096:
                raise ValueError('Unsupported RSA size')
            self.keys[kid] = parsed

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o022:
            raise ValueError('Regular configuration not writable by group or others required')
        if path.stat().st_size > 32768:
            raise ValueError('Configuration size exceeded')
        from .schema import strict_json
        return cls(strict_json(path.read_text()))

    def valid(self, token):
        if not isinstance(token, str) or not token.isascii() or not 1 <= len(token) <= 16384:
            return False
        if not self.observed <= time.time() < self.expires:
            return False
        try:
            header = self.jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or any(k in header for k in ('jku','jwk','x5u','crit')):
                return False
            key = self.keys.get(header.get('kid'))
            if key is None:
                return False
            claims = self.jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                                     audience=self.audience, options={'require':['exp','iat','iss','aud','sub','email']})
            if claims['email'] != self.owner or not isinstance(claims['sub'],str) or not claims['sub']:
                return False
            for name in ('exp','iat','nbf'):
                if name in claims and (type(claims[name]) is not int or not math.isfinite(claims[name])):
                    return False
            return claims['iat'] < claims['exp']
        except (self.jwt.PyJWTError, ValueError, TypeError, OverflowError):
            return False
