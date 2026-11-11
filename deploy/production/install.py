#!/usr/bin/env python3
"""Explicit host installer. Default validates only; never changes tunnel or DNS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT=Path('/home/apexdev/apex-work')
DEST=Path('/etc/systemd/system')
CONFIG=Path('/etc/apex/access-origin.json')
UNITS=('apex-worker.service','apex-console.service')
RENEWAL=('apex-access-jwks.service','apex-access-jwks.timer')
REFRESHER_DEST=Path('/usr/local/lib/apex/refresh_access_jwks.py')
REFRESHER_HASH='5292d85429c11c1d6dfec8b1d356465a77d57b201c1b73b0dd4b487dd63df9a0'
# Reviewed unit bytes are captured once; changed directives cannot race the tests.
UNIT_HASHES={'apex-worker.service': '5c6872fbc225d7de99f147cf17eaddee0e5e91fab827264ab8cb6b8a9f4dceaf', 'apex-console.service': 'ea95eabc34daed31078b837ba61962696622b7da09cd517a511673d8721de96b',
            'apex-access-jwks.service': '69182da360dbb230a7e43438b3a3d32549f45c936ba4d2cf8e919c8c29c26bb5',
            'apex-access-jwks.timer': '5f522df03cbb11fc18cd44dcc764198df96818228e5227d63aa203b630a25055'}
MANIFESTO='3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd'


def run(*args):
    subprocess.run(args,check=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})


def unit_payloads():
    payloads={}
    for name in UNITS+RENEWAL:
        source=ROOT/'deploy/production'/name
        if source.is_symlink() or not source.is_file():raise ValueError('Regular reviewed unit source required')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=UNIT_HASHES[name]:
            raise ValueError('Unit differs from reviewed installer manifest')
        target=DEST/name
        if target.is_symlink():raise ValueError('Existing unit is a symlink')
        if target.exists() and target.read_bytes()!=data:
            raise ValueError('Existing unit differs; review explicit upgrade before overwrite')
        payloads[name]=data
    return payloads


def install_unit(name,data):
    """Atomic publish without overwriting a concurrent administrator's unit."""
    target=DEST/name
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.read_bytes()!=data:raise ValueError('Conflicting existing unit')
        return False
    fd,tmp=tempfile.mkstemp(prefix='.apex-',dir=DEST)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,0o644)
        try:os.link(tmp,target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes()!=data:raise ValueError('Concurrent unit conflict')
            return False
        return True
    finally:
        os.unlink(tmp)


def refresher_payload():
    source=ROOT/'deploy/production/refresh_access_jwks.py'
    if source.is_symlink() or not source.is_file():raise ValueError('Regular refresher source required')
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=REFRESHER_HASH:raise ValueError('Refresher differs from reviewed manifest')
    return data


def install_refresher():
    """Root executes only this verified root-owned copy, never the workspace file."""
    data=refresher_payload()
    parent=REFRESHER_DEST.parent
    if parent.is_symlink():raise ValueError('Refresher directory symlink')
    parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    st=parent.stat()
    if st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Root-owned refresher directory required')
    fd,tmp=tempfile.mkstemp(prefix='.apex-',dir=parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,0o644);os.replace(tmp,REFRESHER_DEST)
    except BaseException:
        if os.path.exists(tmp):os.unlink(tmp)
        raise


def check():
    if ROOT.resolve()!=ROOT:raise ValueError('Canonical workspace required')
    source=ROOT/'docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=MANIFESTO:raise ValueError('Manifesto hash mismatch')
    if (ROOT/'runtime').is_symlink() or (ROOT/'runtime/kernel.sqlite3').is_symlink():
        raise ValueError('Runtime symlink forbidden')
    unit_payloads();refresher_payload()
    return {'status':'BUNDLE_CHECKED_NOT_DEPLOYED','units':list(UNITS),
            'origin_config_present':CONFIG.is_file(),'requires_host_administrator':True,
            'cloudflare':'Separate reviewed plan; no automatic route publication'}


# Executed as apexdev in isolated Python; only stdlib, no project imports.
BACKUP_CODE = r"""
from pathlib import Path
import json,os,sqlite3,time
root=Path('/home/apexdev/apex-work/runtime')
if root.is_symlink() or (root/'kernel.sqlite3').is_symlink():raise ValueError('Runtime symlink')
backups=root/'deployment-backups'
if backups.is_symlink():raise ValueError('Backup symlink')
backups.mkdir(mode=0o700,exist_ok=True)
backup=backups/('kernel-'+str(time.time_ns())+'.sqlite3')
fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600);os.close(fd)
with sqlite3.connect((root/'kernel.sqlite3').as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:
    src.backup(dst)
    if dst.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('Backup verification failed')
print(json.dumps({'backup':str(backup),'integrity':'ok','scope':'LOCAL_SQLITE_BACKUP_NOT_OFFSITE_RESTORE'}))
"""


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--install-dependencies',action='store_true')
    parser.add_argument('--bind-access',action='store_true')
    parser.add_argument('--team');parser.add_argument('--aud');parser.add_argument('--owner')
    args=parser.parse_args()
    result=check()
    if args.bind_access:
        if os.geteuid()!=0 or not sys.flags.isolated:raise PermissionError('Run as root with python3 -I')
        install_refresher()
        run('/usr/bin/python3','-I','-B',str(REFRESHER_DEST),'--init','--team',args.team or '','--aud',args.aud or '','--owner',args.owner or '')
        return
    if not args.apply:
        print(json.dumps(result));return
    if os.geteuid()!=0:raise PermissionError('Authenticated host administrator required')
    if not sys.flags.isolated:raise PermissionError('Root installer must run with python3 -I')
    payloads=unit_payloads()
    if Path('/proc/1/comm').read_text().strip()!='systemd':
        raise PermissionError('Run through authorized host executor, not isolated Codex PID namespace')
    if not CONFIG.is_file() or CONFIG.is_symlink() or CONFIG.stat().st_uid!=0 or CONFIG.stat().st_mode&0o022:
        raise ValueError('Root-owned non-writable-by-others Access configuration required')
    # Validation occurs as the unprivileged runtime owner, never importing project
    # application code as root. Configuration contains public keys, not tokens.
    if args.install_dependencies:
        run('apt-get','update')
        run('apt-get','install','-y','python3','python3-jwt','python3-cryptography','python3-waitress')
    run('runuser','-u','apexdev','--','env','PYTHONPATH='+str(ROOT/'core'),
        '/usr/bin/python3','-B','-c',
        'from apex.kernel.access_auth import AccessVerifier; import waitress; AccessVerifier.load("/etc/apex/access-origin.json")')
    run('runuser','-u','apexdev','--','/usr/bin/python3','-B',str(ROOT/'scripts/test_offline.py'))
    # SQLite paths are controlled by the runtime user. Never open them as root.
    run('runuser','-u','apexdev','--','/usr/bin/python3','-I','-B','-c',BACKUP_CODE)
    install_refresher()
    for name,data in payloads.items():
        install_unit(name,data)
    run('systemctl','daemon-reload')
    run('systemctl','enable','--now','apex-access-jwks.timer')
    run('systemctl','start','apex-access-jwks.service')  # Fresh keys before console start.
    for name in UNITS:
        run('systemctl','enable',name)
        run('systemctl','start',name)
        run('systemctl','is-active','--quiet',name)
    print(json.dumps({'status':'HOST_UNITS_STARTED','backup':'See verified backup receipt above',
                      'public_https':'NOT_VERIFIED','cloudflare_unchanged':True}))


if __name__=='__main__':main()
