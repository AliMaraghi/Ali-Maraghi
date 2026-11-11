#!/usr/bin/env python3
"""Root-run Google runtime provisioning. Standard library only; run with python3 -I.

  python3 -I -B /home/apexdev/apex-work/deploy/production/provision_google.py

Prompts for the OAuth client ID and (hidden) client secret from Google Cloud
Console; never accepts them as arguments (process listings) or prints them.
Owner identity is taken from the bound Access configuration. An existing
encryption key is always preserved; a key is generated only on first binding.
Writes /etc/apex/google-runtime.json atomically as apexdev:apexdev 0600, installs
the reviewed worker drop-in, validates as apexdev, then restarts both services.
"""
import base64
import getpass
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

ROOT = '/home/apexdev/apex-work'
ACCESS = '/etc/apex/access-origin.json'
TARGET = '/etc/apex/google-runtime.json'
REDIRECT = 'https://console.apexcorelab.uk/auth/google/callback'
DROPIN_SRC = ROOT + '/deploy/production/apex-worker.service.d/google-sync.conf.example'
DROPIN_DIR = '/etc/systemd/system/apex-worker.service.d'
DROPIN_HASH = '252d834f1ede3178a3a66230f49f4ff8382d570620ff6b7697ec6fa8c717e163'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}


def run(*args):
    subprocess.run(args, check=True, env=ENV)


def write_atomic(path, data, mode, uid, gid):
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix='.apex-', dir=directory)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main():
    if os.geteuid() != 0 or not sys.flags.isolated:
        raise PermissionError('Run as root with python3 -I')
    st = os.lstat(ACCESS)
    if os.path.islink(ACCESS) or st.st_uid != 0 or st.st_mode & 0o022:
        raise PermissionError('Bound root-owned Access configuration required first')
    with open(ACCESS) as stream:
        owner = json.load(stream)['owner_email']
    dropin = open(DROPIN_SRC, 'rb').read()
    if hashlib.sha256(dropin).hexdigest() != DROPIN_HASH:
        raise ValueError('Worker drop-in differs from reviewed hash')
    service = pwd.getpwnam('apexdev')
    prior = {}
    if os.path.lexists(TARGET):
        if os.path.islink(TARGET):
            raise PermissionError('Configuration symlink refused')
        with open(TARGET) as stream:
            prior = json.load(stream)
        if prior.get('owner') != owner:
            raise ValueError('Existing Google config belongs to a different owner; review manually')
    print('Owner (from Access binding):', owner)
    client_id = input('OAuth client ID (ends with .apps.googleusercontent.com): ').strip()
    if not re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', client_id):
        raise ValueError('Unexpected client ID format')
    secret = getpass.getpass('OAuth client secret (hidden): ').strip()
    if not 8 <= len(secret) <= 512 or any(c.isspace() for c in secret):
        raise ValueError('Unexpected client secret format')
    print('Synced Gmail metadata (From/To/Subject/Date) includes third-party correspondents.')
    if input('Type REVIEWED to confirm private metadata import for 30-day retention: ').strip() != 'REVIEWED':
        raise PermissionError('Private import review not confirmed')
    # Preserve any existing key: replacing it would orphan encrypted tokens and sync state.
    key = prior.get('encryption_key') or base64.urlsafe_b64encode(os.urandom(32)).decode()
    config = {'owner': owner, 'client_id': client_id, 'client_secret': secret, 'redirect_uri': REDIRECT,
              'encryption_key': key, 'review_reference': prior.get('review_reference', 'founder-gmail-metadata-20261111'),
              'retention_days': 30, 'mixed_content_reviewed': True}
    write_atomic(TARGET, json.dumps(config, sort_keys=True).encode(), 0o600, service.pw_uid, service.pw_gid)
    # Validate exactly as the console will, as the unprivileged service user.
    run('runuser', '-u', 'apexdev', '--', 'env', 'PYTHONPATH=' + ROOT + '/core', '/usr/bin/python3', '-B', '-c',
        'from apex.google_web import load_config; load_config("' + TARGET + '", "' + owner + '")')
    os.makedirs(DROPIN_DIR, mode=0o755, exist_ok=True)
    write_atomic(DROPIN_DIR + '/google-sync.conf', dropin, 0o644, 0, 0)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'restart', 'apex-console.service', 'apex-worker.service')
    run('systemctl', 'is-active', '--quiet', 'apex-console.service')
    run('systemctl', 'is-active', '--quiet', 'apex-worker.service')
    print(json.dumps({'status': 'GOOGLE_RUNTIME_PROVISIONED', 'key_preserved': bool(prior.get('encryption_key')),
                      'next': 'Open https://console.apexcorelab.uk/connections/google and connect'}))


if __name__ == '__main__':
    main()
