#!/usr/bin/env python3
"""Nightly consistent snapshot of runtime/kernel.sqlite3 into backups/ (same machine).

Uses SQLite's online backup API, so it is safe while apex-voice / the agents are writing - a
plain `cp` of a live database is not. Snapshots are 0600 in a 0700 folder, verified with
PRAGMA integrity_check, and pruned after KEEP_DAYS. backups/ matches .gitignore (*.sqlite*).
This protects against corruption and bad writes, NOT against losing the server: copy the
folder off the machine (scp) for that.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEEP_DAYS = 14


def main() -> int:
    source = ROOT / "runtime" / "kernel.sqlite3"
    if not source.is_file():
        print("backup: no runtime/kernel.sqlite3 - nothing to back up", file=sys.stderr)
        return 1
    os.umask(0o077)
    folder = ROOT / "backups"
    folder.mkdir(mode=0o700, exist_ok=True)
    target = folder / time.strftime("kernel-%Y%m%d-%H%M%S.sqlite3", time.gmtime())
    partial = target.with_suffix(".partial")
    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(partial)
    try:
        src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        dst.close()
        src.close()
    if not ok:
        partial.unlink(missing_ok=True)
        print("backup: integrity_check FAILED - snapshot discarded", file=sys.stderr)
        return 1
    partial.rename(target)
    cutoff = time.time() - KEEP_DAYS * 86400
    removed = 0
    for old in folder.glob("kernel-*.sqlite3"):
        if old != target and old.stat().st_mtime < cutoff:
            old.unlink()
            removed += 1
    print(f"backup: wrote {target.name} ({target.stat().st_size} bytes), pruned {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
