"""Encrypted off-site copy of the journal in the owner's own Google Drive.

Why: every record lives on one disk. This puts one encrypted snapshot a day somewhere else.

What leaves the server: a single file, already encrypted here with a passphrase that only the
owner holds a copy of. Google stores ciphertext; without the passphrase it is unreadable, and
without the passphrase the owner cannot restore either - losing it loses the backup.

Access: the Drive scope is drive.file, which reaches only files this application created. It
cannot list, read or change anything else in the owner's Drive.

Runs from the supervised worker (kernel/worker.py), at most once a day, only when all three
are true: the worker has the Google configuration, the owner has granted the Drive scope, and
the passphrase file exists. Otherwise it does nothing and status() says which one is missing.

Restore, on any machine with openssl (docs/BACKUP_RESTORE.md):
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in FILE -out journal.sqlite3.gz -pass stdin
"""
import gzip
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from .kernel.policy import enforce_durable_stop
from .kernel.schema import strict_json
from .sources.public_http import Connection, resolve_public

HOST = 'www.googleapis.com'
DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
PASSPHRASE_FILE = '/etc/apex/backup-passphrase'
INTERVAL = 86400          # one successful upload a day
RETRY_AFTER = 3600        # after a failure, wait an hour before the next attempt
KEEP = 14                 # uploads kept in Drive; older ones this application made are removed
MAX_BYTES = 64 * 1024 * 1024
ITERATIONS = '600000'
TOKEN = re.compile(r'[A-Za-z0-9._~+/=-]{1,4096}')
FILE_ID = re.compile(r'[A-Za-z0-9_-]{10,128}')


class BackupError(Exception):
    """Carries a fixed code only; never a provider body, a path or key material."""


def _tables(ledger):
    ledger.db.execute('''CREATE TABLE IF NOT EXISTS offsite_backup (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), last_attempt INTEGER NOT NULL,
        last_success INTEGER, last_state TEXT NOT NULL, bytes INTEGER, sha256 TEXT)''')
    ledger.db.execute('''CREATE TABLE IF NOT EXISTS offsite_backup_files (
        file_id TEXT PRIMARY KEY, created INTEGER NOT NULL)''')


def passphrase_ready(path=PASSPHRASE_FILE):
    """A private regular file owned by the service account, holding at least 20 characters.
    The content is never read here."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077
            and info.st_uid == os.geteuid() and info.st_size >= 20)


def status(ledger, scope, passphrase_file=PASSPHRASE_FILE):
    """One plain line for the owner's connection page."""
    _tables(ledger)
    row = ledger.db.execute('SELECT last_attempt,last_success,last_state,bytes FROM offsite_backup').fetchone()
    if DRIVE_SCOPE not in (scope or '').split():
        return 'Off-site backup: waiting for Drive permission (press Connect / reconnect Google once).'
    if not passphrase_ready(passphrase_file):
        return 'Off-site backup: waiting for the passphrase file on the server.'
    if not row:
        return 'Off-site backup: ready, first run within a few minutes.'
    stamp = lambda value: time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(value))
    if row[1]:
        tail = '' if row[2] == 'UPLOADED' else '; latest attempt ' + stamp(row[0]) + ' ' + row[2]
        return 'Off-site backup: last upload ' + stamp(row[1]) + ', ' + str(row[3]) + ' bytes encrypted' + tail + '.'
    return 'Off-site backup: no upload yet; latest attempt ' + stamp(row[0]) + ' ' + row[2] + '.'


def snapshot(root, workdir):
    """A consistent copy through SQLite's backup API, checked before it is trusted."""
    source = Path(root) / 'runtime' / 'kernel.sqlite3'
    target = Path(workdir) / 'journal.sqlite3'
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        healthy = dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        dst.close()
        src.close()
    if not healthy:
        raise BackupError('SNAPSHOT_INTEGRITY_FAILED')
    return target


def encrypt(path, passphrase_file=PASSPHRASE_FILE):
    """gzip, then AES-256 with a PBKDF2 key from the owner's passphrase. openssl reads the
    passphrase from the file itself, so it never enters this process or a command line."""
    packed = gzip.compress(Path(path).read_bytes(), 6)
    try:
        result = subprocess.run(
            ['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-iter', ITERATIONS, '-salt', '-pass', 'file:' + passphrase_file],
            input=packed, capture_output=True, timeout=300, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    except (OSError, subprocess.SubprocessError):
        raise BackupError('ENCRYPTION_UNAVAILABLE') from None
    if result.returncode or not result.stdout.startswith(b'Salted__'):
        raise BackupError('ENCRYPTION_FAILED')
    if len(result.stdout) > MAX_BYTES:
        raise BackupError('SNAPSHOT_TOO_LARGE')
    return result.stdout


def _call(method, path, token, body=None, content_type=None):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise BackupError('INVALID_TOKEN')
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.connect()
        conn.sock.settimeout(180)          # a multi-megabyte body needs longer than the 5 s default
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json',
                   'Accept-Encoding': 'identity', 'Connection': 'close'}
        if body is not None:
            headers['Content-Type'] = content_type
            headers['Content-Length'] = str(len(body))
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        raw = response.read(65537)
        return response.status, raw
    except BackupError:
        raise
    except Exception:
        raise BackupError('DRIVE_UNREACHABLE') from None
    finally:
        conn.close()


def upload(token, name, blob):
    """One multipart create. Returns the new file's id."""
    if not re.fullmatch(r'[a-z0-9.-]{8,80}', name):
        raise BackupError('INVALID_NAME')
    boundary = 'apex' + hashlib.sha256(os.urandom(16)).hexdigest()[:24]
    body = (('--' + boundary + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'
             + json.dumps({'name': name, 'description': 'APEX encrypted journal backup'})
             + '\r\n--' + boundary + '\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            + blob + ('\r\n--' + boundary + '--\r\n').encode())
    code, raw = _call('POST', '/upload/drive/v3/files?uploadType=multipart&fields=id', token, body,
                      'multipart/related; boundary=' + boundary)
    if code == 403:
        raise BackupError('DRIVE_REFUSED_CHECK_API_ENABLED')
    if code != 200 or len(raw) > 65536:
        raise BackupError('DRIVE_UPLOAD_REJECTED')
    try:
        file_id = strict_json(raw.decode())['id']
    except Exception:
        raise BackupError('DRIVE_REPLY_INVALID') from None
    if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
        raise BackupError('DRIVE_REPLY_INVALID')
    return file_id


def remove(token, file_id):
    """Deletes one earlier upload of ours. A file already gone counts as removed."""
    if not FILE_ID.fullmatch(file_id):
        return False
    code, _ = _call('DELETE', '/drive/v3/files/' + file_id, token)
    return code in (204, 404)


def run_if_due(ledger, root, scope, token_supplier, now=None, passphrase_file=PASSPHRASE_FILE,
               uploader=upload, remover=remove):
    """Returns None when there is nothing to do, else the state it recorded."""
    now = int(time.time()) if now is None else now
    if DRIVE_SCOPE not in (scope or '').split() or not passphrase_ready(passphrase_file):
        return None
    with ledger.transaction():
        enforce_durable_stop(ledger)
        _tables(ledger)
        row = ledger.db.execute('SELECT last_attempt,last_success FROM offsite_backup').fetchone()
        if row and ((row[1] and now - row[1] < INTERVAL) or now - row[0] < RETRY_AFTER):
            return None
        # Claim the attempt first: a crash mid-upload must not turn into an upload every minute.
        ledger.db.execute('''INSERT INTO offsite_backup VALUES(1,?,NULL,'STARTED',NULL,NULL)
            ON CONFLICT(singleton) DO UPDATE SET last_attempt=excluded.last_attempt,last_state='STARTED' ''', (now,))
    state, size, digest, file_id = 'FAILED', None, None, None
    try:
        with tempfile.TemporaryDirectory(prefix='apex-backup-', dir=str(Path(root) / 'runtime')) as workdir:
            os.chmod(workdir, 0o700)
            blob = encrypt(snapshot(root, workdir), passphrase_file)
        size, digest = len(blob), hashlib.sha256(blob).hexdigest()
        token = token_supplier()
        file_id = uploader(token, 'apex-journal-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime(now)) + '.sqlite3.gz.enc', blob)
        state = 'UPLOADED'
    except BackupError as failure:
        state = str(failure)
    except Exception as failure:
        state = 'FAILED_' + type(failure).__name__.upper()[:40]
    stale = []
    with ledger.transaction():
        if state == 'UPLOADED':
            ledger.db.execute('UPDATE offsite_backup SET last_success=?,last_state=?,bytes=?,sha256=?', (now, state, size, digest))
            ledger.db.execute('INSERT OR IGNORE INTO offsite_backup_files VALUES(?,?)', (file_id, now))
            stale = [r[0] for r in ledger.db.execute(
                'SELECT file_id FROM offsite_backup_files ORDER BY created DESC LIMIT -1 OFFSET ?', (KEEP,))]
        else:
            ledger.db.execute('UPDATE offsite_backup SET last_state=?', (state,))
        ledger._append('offsite-backup-' + str(now), 'decision', 'personal',
                       {'phase': 'OFFSITE_BACKUP', 'state': state, 'bytes': size, 'sha256': digest,
                        'destination': 'owner-google-drive', 'encrypted': True})
    for old in stale[:3]:                       # bounded tidy-up; the rest go on later days
        try:
            if remover(token, old):
                with ledger.transaction():
                    ledger.db.execute('DELETE FROM offsite_backup_files WHERE file_id=?', (old,))
        except Exception:
            break
    return state
