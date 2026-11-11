#!/usr/bin/env python3
"""Root-run Meta runtime provisioning. Standard library only; run with python3 -I.

  python3 -I -B /home/apexdev/apex-work/deploy/production/provision_meta.py

Prompts for the Meta App ID, Graph API version and (hidden) App secret from the
Meta App Dashboard; never accepts them as arguments (process listings) or prints them.
Owner identity is taken from the bound Access configuration. An existing
encryption key is always preserved; a key is generated only on first binding.
Writes /etc/apex/google-runtime.json atomically as apexdev:apexdev 0600, validates
as apexdev, then restarts the console.
"""
import base64
import getpass
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

ROOT = '/home/apexdev/apex-work'
ACCESS = '/etc/apex/access-origin.json'
TARGET = '/etc/apex/meta-runtime.json'
REDIRECT = 'https://console.apexcorelab.uk/auth/google/callback'
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
    service = pwd.getpwnam('apexdev')
    prior = {}
    if os.path.lexists(TARGET):
        if os.path.islink(TARGET):
            raise PermissionError('Configuration symlink refused')
        with open(TARGET) as stream:
            prior = json.load(stream)
        if prior.get('owner') != owner:
            raise ValueError('Existing Meta config belongs to a different owner; review manually')
    print('Owner (from Access binding):', owner)
    app_id = input('Meta App ID (digits): ').strip()
    if not re.fullmatch(r'[0-9]{5,40}', app_id):
        raise ValueError('Unexpected App ID format')
    version = input('Graph API version shown in App Dashboard (e.g. v21.0): ').strip()
    if not re.fullmatch(r'v[0-9]{1,3}\.0', version):
        raise ValueError('Unexpected Graph version format')
    secret = getpass.getpass('Meta App secret (hidden): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9]{16,128}', secret):
        raise ValueError('Unexpected App secret format')
    if input('Type REVIEWED to confirm read-only Page/Instagram discovery import: ').strip() != 'REVIEWED':
        raise PermissionError('Privacy review not confirmed')
    key = prior.get('encryption_key') or base64.urlsafe_b64encode(os.urandom(32)).decode()
    config = {'owner': owner, 'app_id': app_id, 'app_secret': secret, 'graph_version': version,
              'encryption_key': key, 'privacy_review': prior.get('privacy_review', 'founder-meta-readonly-20261111')}
    write_atomic(TARGET, json.dumps(config, sort_keys=True).encode(), 0o600, service.pw_uid, service.pw_gid)
    run('runuser', '-u', 'apexdev', '--', 'env', 'PYTHONPATH=' + ROOT + '/core', '/usr/bin/python3', '-B', '-c',
        'from apex.meta_web import MetaRoutes; MetaRoutes("' + ROOT + '", "' + TARGET + '", "' + owner + '")')
    run('systemctl', 'restart', 'apex-console.service')
    run('systemctl', 'is-active', '--quiet', 'apex-console.service')
    print(json.dumps({'status': 'META_RUNTIME_PROVISIONED', 'key_preserved': bool(prior.get('encryption_key')),
                      'next': 'Open https://console.apexcorelab.uk/connections/meta and connect'}))


if __name__ == '__main__':
    main()
