#!/usr/bin/env python3
"""Root-run Cloudflare Access public-key snapshot writer. Standard library only.

Installed by install.py as a root-owned copy; never execute the workspace copy as
root. Fetches only <issuer>/cdn-cgi/access/certs (public keys, no secrets), keeps
the existing file on any failure (the console then fails closed at expiry), and
atomically replaces /etc/apex/access-origin.json (root:root 0644).

Initial binding (owner-provided public identifiers):
  python3 -I -B refresh_access_jwks.py --init --team TEAM --aud AUD --owner EMAIL
Renewal (timer): python3 -I -B refresh_access_jwks.py
"""
import argparse
import json
import os
import re
import ssl
import tempfile
import time
import urllib.request

CONFIG = '/etc/apex/access-origin.json'
LIFETIME = 43200  # Verifier accepts <= 86400; hourly renewal leaves ample margin.


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Redirect refused')


def validate_identity(issuer, audience, owner):
    if not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com', issuer or ''):
        raise ValueError('Exact Cloudflare Access team issuer required')
    if not re.fullmatch(r'[a-f0-9]{64}', audience or ''):
        raise ValueError('64-hex application AUD required')
    if not re.fullmatch(r'[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+', owner or ''):
        raise ValueError('One exact owner email required')


def fetch_keys(issuer, opener=None):
    url = issuer + '/cdn-cgi/access/certs'
    opener = opener or urllib.request.build_opener(
        NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(urllib.request.Request(url, headers={'Accept': 'application/json'}), timeout=15) as response:
        if response.status != 200:
            raise ValueError('Unexpected status')
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError('Certificate document too large')
    keys = json.loads(body)['keys']
    if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
        raise ValueError('Bounded JWKS required')
    public = []
    seen = set()
    for key in keys:
        if (not isinstance(key, dict) or key.get('kty') != 'RSA' or key.get('alg') != 'RS256'
                or key.get('use') != 'sig' or 'd' in key or not isinstance(key.get('kid'), str)
                or not 1 <= len(key['kid']) <= 128 or key['kid'] in seen
                or not all(isinstance(key.get(f), str) and 1 <= len(key[f]) <= 1024 for f in ('n', 'e'))):
            raise ValueError('Public RS256 signing keys required')
        seen.add(key['kid'])
        public.append({f: key[f] for f in ('kid', 'kty', 'alg', 'use', 'n', 'e')})
    return url, public


def build(issuer, audience, owner, now, opener=None):
    validate_identity(issuer, audience, owner)
    url, keys = fetch_keys(issuer, opener)
    return {'issuer': issuer, 'audience': audience, 'owner_email': owner,
            'retrieved_at': now, 'expires_at': now + LIFETIME,
            'source_url': url, 'jwks': {'keys': keys}}


def write_atomic(path, config):
    directory = os.path.dirname(path)
    st = os.lstat(directory)
    if not os.path.isdir(directory) or os.path.islink(directory) or st.st_uid != 0 or st.st_mode & 0o022:
        raise PermissionError('Root-owned non-writable-by-others config directory required')
    fd, tmp = tempfile.mkstemp(prefix='.access-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(config, out, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def existing(path):
    if os.path.islink(path):
        raise PermissionError('Configuration symlink refused')
    st = os.stat(path)
    if st.st_uid != 0 or st.st_mode & 0o022 or st.st_size > 32768:
        raise PermissionError('Root-owned protected configuration required')
    with open(path) as stream:
        return json.load(stream)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--team')
    parser.add_argument('--aud')
    parser.add_argument('--owner')
    parser.add_argument('--config', default=CONFIG)
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise PermissionError('Root required to write protected Access configuration')
    now = int(time.time())
    if args.init:
        issuer = 'https://' + (args.team or '') + '.cloudflareaccess.com'
        if os.path.lexists(args.config):
            prior = existing(args.config)
            if (prior.get('issuer'), prior.get('audience'), prior.get('owner_email')) != (issuer, args.aud, args.owner):
                raise ValueError('Existing binding differs; remove it deliberately before rebinding')
        os.makedirs(os.path.dirname(args.config), mode=0o755, exist_ok=True)
        config = build(issuer, args.aud, args.owner, now)
    else:
        prior = existing(args.config)
        config = build(prior['issuer'], prior['audience'], prior['owner_email'], now)
    write_atomic(args.config, config)
    print(json.dumps({'status': 'ACCESS_KEYS_REFRESHED', 'issuer': config['issuer'],
                      'keys': len(config['jwks']['keys']), 'expires_at': config['expires_at']}))


if __name__ == '__main__':
    main()
