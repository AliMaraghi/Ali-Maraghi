# Off-site backup and restore

One encrypted copy of `runtime/kernel.sqlite3` goes to the owner's own Google Drive once a day
(`core/apex/drive_backup.py`, run by the supervised worker). The last 14 are kept.

## What must exist before it runs

1. Google connected with the Drive permission: press **Connect / reconnect Google** once on
   `console.apexcorelab.uk/connections/google` after this version is installed. The permission is
   `drive.file`: it reaches only files APEX itself created.
2. The Drive API enabled in the Google Cloud project that owns the OAuth client.
3. A passphrase file on the server, `/etc/apex/backup-passphrase`, owned by `apexdev`, mode 600,
   at least 20 characters. **The owner must keep a copy of this passphrase somewhere off the
   server.** Without it the backups cannot be decrypted by anyone.

The connection page shows which of these is still missing, and the time and size of the last upload.

## Restore

Download the newest `apex-journal-*.sqlite3.gz.enc` from Drive, then on any machine with openssl:

    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in FILE -out journal.sqlite3.gz
    gunzip journal.sqlite3.gz

openssl asks for the passphrase. The result is the journal as it was at upload time. Check it
with `sqlite3 journal.sqlite3 "PRAGMA integrity_check"` before putting it in `runtime/`.

## Not covered

Only the journal is copied. Files under `runtime/inbox` (persona samples, exports) and `/etc/apex`
(keys, OAuth client) are not; a restored server needs Google reconnected and keys re-provisioned.
A restore has been tested offline (`tests/test_drive_backup.py`), not yet from a real Drive file.
