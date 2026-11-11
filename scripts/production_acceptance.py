"""Read-only live production acceptance probe. Unprivileged; changes nothing.

Owner login itself needs a human browser session through Cloudflare Access and is
reported as MANUAL_REQUIRED; this probe proves the surrounding fail-closed facts.
"""
import http.client
import json
import os
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = 'console.apexcorelab.uk'
CONFIG = Path('/etc/apex/access-origin.json')
UNITS = ('apex-console.service', 'apex-worker.service', 'apex-access-jwks.timer')


def units():
    out = {}
    for unit in UNITS:
        props = subprocess.run(['systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState',
                                '-p', 'UnitFileState', '-p', 'NRestarts'],
                               capture_output=True, text=True, timeout=10).stdout
        p = dict(line.split('=', 1) for line in props.splitlines() if '=' in line)
        out[unit] = {'ok': p.get('ActiveState') == 'active' and p.get('UnitFileState') == 'enabled', **p}
    return out


def access_config():
    try:
        st = CONFIG.lstat()
        cfg = json.loads(CONFIG.read_text())
        ttl = cfg['expires_at'] - int(time.time())
        ok = (not CONFIG.is_symlink() and st.st_uid == 0 and not st.st_mode & 0o022 and ttl > 0)
        return {'ok': ok, 'issuer': cfg['issuer'], 'keys': len(cfg['jwks']['keys']), 'ttl_seconds': ttl,
                'root_owned': st.st_uid == 0, 'mode': oct(st.st_mode & 0o777)}
    except (OSError, ValueError, KeyError) as error:
        return {'ok': False, 'error': type(error).__name__}


def origin_denial():
    results = {}
    for name, token in (('no_token', None), ('forged_token', 'eyJhbGciOiJSUzI1NiIsImtpZCI6IngifQ.eyJlbWFpbCI6IngifQ.AAAA')):
        try:
            conn = http.client.HTTPConnection('127.0.0.1', 8765, timeout=5)
            conn.request('GET', '/console', headers={} if token is None else {'Cf-Access-Jwt-Assertion': token})
            results[name] = conn.getresponse().status
        except OSError as error:
            results[name] = type(error).__name__
    return {'ok': all(v == 401 for v in results.values()), **results}


def public_edge(issuer):
    try:
        addresses = sorted({a[4][0] for a in socket.getaddrinfo(HOST, 443, proto=socket.IPPROTO_TCP)})
    except socket.gaierror as error:
        return {'ok': False, 'dns': 'UNRESOLVED', 'errno': error.errno}
    try:
        conn = http.client.HTTPSConnection(HOST, 443, timeout=10, context=ssl.create_default_context())
        conn.request('GET', '/console')
        response = conn.getresponse()
        location = response.getheader('Location') or ''
        # Unauthenticated request must be redirected to the Access login, never served.
        gated = response.status in (302, 303) and issuer is not None and location.startswith(issuer + '/')
        return {'ok': gated, 'dns': len(addresses), 'tls': 'VERIFIED', 'status': response.status,
                'redirects_to_access': gated}
    except (OSError, ssl.SSLError) as error:
        return {'ok': False, 'dns': len(addresses), 'error': type(error).__name__}


def worker_health():
    db = ROOT / 'runtime/kernel.sqlite3'
    try:
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
            row = conn.execute('SELECT observed_at,state,interval_seconds FROM worker_health WHERE singleton=1').fetchone()
    except sqlite3.Error as error:
        return {'ok': False, 'error': type(error).__name__}
    if row is None:
        return {'ok': False, 'state': 'NOT_OBSERVED'}
    age = int(time.time()) - row[0]
    return {'ok': row[1] in ('CYCLE_COMPLETED', 'STOPPED') and 0 <= age <= row[2] * 2,
            'state': row[1], 'age_seconds': age}


def main():
    access = access_config()
    checks = {'units': units(), 'access_config': access, 'origin_denial': origin_denial(),
              'public_edge': public_edge(access.get('issuer')), 'worker_health': worker_health()}
    automatic = all(c['ok'] for c in checks['units'].values()) and all(
        checks[k]['ok'] for k in ('access_config', 'origin_denial', 'public_edge', 'worker_health'))
    print(json.dumps({'observed_at': int(time.time()), 'checks': checks,
                      'automatic_checks': 'PASS' if automatic else 'FAIL',
                      'owner_browser_login': 'MANUAL_REQUIRED',
                      'scope': 'LIVE_READ_ONLY_PROBE_NOT_PROVIDER_AUTHORIZATION'}, indent=1))
    return 0 if automatic else 1


if __name__ == '__main__':
    sys.exit(main())
