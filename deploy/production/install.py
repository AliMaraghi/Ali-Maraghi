#!/usr/bin/env python3
"""Explicit host installer. Default validates only; never changes tunnel or DNS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import subprocess
import tempfile
import time

ROOT=Path('/home/apexdev/apex-work')
DEST=Path('/etc/systemd/system')
CONFIG=Path('/etc/apex/access-origin.json')
UNITS=('apex-worker.service','apex-console.service')
MANIFESTO='3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd'


def run(*args):
    subprocess.run(args,check=True)


def check():
    if ROOT.resolve()!=ROOT:raise ValueError('Canonical workspace required')
    source=ROOT/'docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=MANIFESTO:raise ValueError('Manifesto hash mismatch')
    if (ROOT/'runtime').is_symlink() or (ROOT/'runtime/kernel.sqlite3').is_symlink():
        raise ValueError('Runtime symlink forbidden')
    for name in UNITS:
        data=(ROOT/'deploy/production'/name).read_bytes()
        target=DEST/name
        if target.is_symlink():raise ValueError('Existing unit is a symlink')
        if target.exists() and target.read_bytes()!=data:
            raise ValueError('Existing unit differs; review explicit upgrade before overwrite')
    return {'status':'BUNDLE_CHECKED_NOT_DEPLOYED','units':list(UNITS),
            'origin_config_present':CONFIG.is_file(),'requires_host_administrator':True,
            'cloudflare':'Separate reviewed plan; no automatic route publication'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--install-dependencies',action='store_true')
    args=parser.parse_args()
    result=check()
    if not args.apply:
        print(json.dumps(result));return
    if os.geteuid()!=0:raise PermissionError('Authenticated host administrator required')
    if Path('/proc/1/comm').read_text().strip()!='systemd':
        raise PermissionError('Run through authorized host executor, not isolated Codex PID namespace')
    if not CONFIG.is_file() or CONFIG.is_symlink() or CONFIG.stat().st_uid!=0 or CONFIG.stat().st_mode&0o022:
        raise ValueError('Root-owned non-writable-by-others Access configuration required')
    # Validation occurs as the unprivileged runtime owner, never importing project
    # application code as root. Configuration contains public keys, not tokens.
    if args.install_dependencies:
        run('apt-get','update')
        run('apt-get','install','-y','python3','python3-jwt','python3-cryptography')
    run('runuser','-u','apexdev','--','env','PYTHONPATH='+str(ROOT/'core'),
        '/usr/bin/python3','-B','-c',
        'from apex.kernel.access_auth import AccessVerifier; AccessVerifier.load("/etc/apex/access-origin.json")')
    run('runuser','-u','apexdev','--','/usr/bin/python3','-B',str(ROOT/'scripts/test_offline.py'))
    # Consistent backup through SQLite backup API, never copying an open database.
    backups=ROOT/'runtime/deployment-backups'
    if backups.is_symlink():raise ValueError('Backup symlink forbidden')
    backups.mkdir(mode=0o700,exist_ok=True)
    backup=backups/('kernel-'+str(time.time_ns())+'.sqlite3')
    fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    with sqlite3.connect((ROOT/'runtime/kernel.sqlite3').as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('Backup verification failed')
    for name in UNITS:
        target=DEST/name
        data=(ROOT/'deploy/production'/name).read_bytes()
        if target.exists():continue  # Existing identical units are preserved.
        fd,tmp=tempfile.mkstemp(prefix='.apex-',dir=DEST)
        try:
            with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            os.chmod(tmp,0o644);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    run('systemctl','daemon-reload')
    for name in UNITS:
        run('systemctl','enable',name)
        run('systemctl','start',name)
        run('systemctl','is-active','--quiet',name)
    print(json.dumps({'status':'HOST_UNITS_STARTED','backup':str(backup),
                      'public_https':'NOT_VERIFIED','cloudflare_unchanged':True}))


if __name__=='__main__':main()
