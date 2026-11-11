#!/usr/bin/env python3
"""Root-run Financial (Enable Banking) runtime provisioning. Standard library only; run with python3 -I.

  python3 -I -B /home/apexdev/apex-work/deploy/production/provision_finance.py

Step 1 (no app yet): generates an RSA key ON THIS SERVER and prints only the public
certificate to register in the Enable Banking Control Panel. Step 2: binds the
application ID. Statement import works after step 1 alone; never accepts them as arguments (process listings) or prints them.
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
TARGET = '/etc/apex/finance-runtime.json'
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


def generate_key():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'APEX founder read-only AIS')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=730)).sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return pem, cert.public_bytes(serialization.Encoding.PEM).decode()


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
            raise ValueError('Existing finance config belongs to a different owner; review manually')
    print('Owner (from Access binding):', owner)
    config = {'owner': owner, 'encryption_key': prior.get('encryption_key') or base64.urlsafe_b64encode(os.urandom(32)).decode()}
    pem = prior.get('private_key_pem')
    if not pem:
        source = input('Path to an Enable Banking private key .pem already on this server (Enter = generate here): ').strip()
        if source:
            with open(source) as stream:
                pem = stream.read(20000)
            if 'PRIVATE KEY' not in pem:
                raise ValueError('Not a PEM private key')
        else:
            pem, cert = generate_key()
            print('\nRegister THIS PUBLIC certificate in the Enable Banking Control Panel (safe to share):\n')
            print(cert)
    config['private_key_pem'] = pem
    app_id = input('Enable Banking application ID (UUID; Enter to bind later): ').strip() or prior.get('enablebanking_app_id')
    if app_id:
        if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', app_id):
            raise ValueError('Application ID must be a lowercase UUID')
        config['enablebanking_app_id'] = app_id
    write_atomic(TARGET, json.dumps(config, sort_keys=True).encode(), 0o600, service.pw_uid, service.pw_gid)
    run('runuser', '-u', 'apexdev', '--', 'env', 'PYTHONPATH=' + ROOT + '/core', '/usr/bin/python3', '-B', '-c',
        'from apex.finance_web import FinanceRoutes; FinanceRoutes("' + ROOT + '", "' + TARGET + '", "' + owner + '")')
    run('systemctl', 'restart', 'apex-console.service')
    run('systemctl', 'is-active', '--quiet', 'apex-console.service')
    print(json.dumps({'status': 'FINANCE_RUNTIME_PROVISIONED', 'key_preserved': bool(prior.get('encryption_key')),
                      'application_bound': bool(app_id),
                      'next': 'Open https://console.apexcorelab.uk/connections/finance'}))


if __name__ == '__main__':
    main()
