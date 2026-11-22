#!/usr/bin/env python3
"""Isolated restore drill. Never touches the live database or Google Drive.

Takes a consistent snapshot of the live journal (read-only), encrypts it exactly as the off-site backup does,
decrypts it again with the same passphrase file, unpacks it into a private temporary folder, and reconciles the
restored copy against the live one table by table. This proves the backup FORMAT can be restored with the passphrase
held on the server. It does not download the copy stored in Google Drive, so that copy remains unproven."""
from __future__ import annotations

import gzip
import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))


def _counts(path) -> dict:
    db = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        return {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
                for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    finally:
        db.close()


def drill(root=ROOT, passphrase_file=None) -> dict:
    from apex import drive_backup as b
    passphrase_file = passphrase_file or b.PASSPHRASE_FILE
    report = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "live_database_modified": False, "drive_copy_tested": False}
    if not b.passphrase_ready(passphrase_file):
        return {**report, "status": "BLOCKED", "reason": "the passphrase file is missing or not readable by this service"}
    with tempfile.TemporaryDirectory(prefix="apex-restore-drill-") as work:
        snap = b.snapshot(root, work)
        plain = Path(snap).read_bytes()
        blob = b.encrypt(snap, passphrase_file)
        out = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", b.ITERATIONS, "-pass", "file:" + passphrase_file],
                             input=blob, capture_output=True, timeout=300, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
        if out.returncode:
            return {**report, "status": "FAILED", "reason": "decryption failed"}
        restored = Path(work) / "restored.sqlite3"
        restored.write_bytes(gzip.decompress(out.stdout))
        db = sqlite3.connect(restored)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        db.close()
        live_before, back = _counts(snap), _counts(restored)
        diff = {t: [live_before.get(t), back.get(t)] for t in sorted(set(live_before) | set(back)) if live_before.get(t) != back.get(t)}
        report.update({"status": "PASS" if integrity == "ok" and not diff and hashlib.sha256(plain).digest() == hashlib.sha256(restored.read_bytes()).digest() else "FAILED",
                       "encrypted_bytes": len(blob), "restored_bytes": restored.stat().st_size, "integrity": integrity,
                       "byte_identical_to_snapshot": hashlib.sha256(plain).hexdigest() == hashlib.sha256(restored.read_bytes()).hexdigest(),
                       "tables": len(back), "rows_restored": sum(back.values()), "table_differences": diff,
                       "events_restored": back.get("events"), "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(drill(), indent=1))
