#!/usr/bin/env python3
"""Salvage a malformed runtime/kernel.sqlite3 without ever deleting the original.

salvage(root): copies the damaged file to runtime/recovery/, then copies every readable row of every table into a
               fresh database beside it and reports, per table, how many rows were saved and where reading broke.
swap(root):    only if the salvaged copy passes SQLite's integrity check, puts it in place of the live file. The damaged
               original stays in runtime/recovery/.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from pathlib import Path


def _paths(root):
    rt = Path(root) / "runtime"
    rec = rt / "recovery"
    rec.mkdir(mode=0o700, exist_ok=True)
    return rt / "kernel.sqlite3", rec


def _copy_table(src, dst, name: str) -> dict:
    saved, breaks, last = 0, [], None
    cols = [r[1] for r in src.execute(f'PRAGMA table_info("{name}")')]
    marks = ",".join("?" * len(cols))
    def run(sql, args=()):
        nonlocal saved, last
        cur = src.execute(sql, args)
        while True:
            row = cur.fetchone()
            if row is None:
                return
            dst.execute(f'INSERT OR IGNORE INTO "{name}" VALUES ({marks})', row[1:])
            saved, last = saved + 1, row[0]
    try:
        try:
            run(f'SELECT rowid, * FROM "{name}" ORDER BY rowid')
        except sqlite3.DatabaseError as exc:
            breaks.append(f"forward stop after rowid {last}: {str(exc)[:60]}")
            floor = last or 0
            try:                                                   # read the tail backwards down to the break
                run(f'SELECT rowid, * FROM "{name}" WHERE rowid > ? ORDER BY rowid DESC', (floor,))
            except sqlite3.DatabaseError as exc2:
                breaks.append(f"backward stop at rowid {last}: {str(exc2)[:60]}")
    except sqlite3.OperationalError:                               # WITHOUT ROWID table
        try:
            for row in src.execute(f'SELECT * FROM "{name}"'):
                dst.execute(f'INSERT OR IGNORE INTO "{name}" VALUES ({marks})', row)
                saved += 1
        except sqlite3.DatabaseError as exc:
            breaks.append(str(exc)[:60])
    return {"saved": saved, "breaks": breaks}


def salvage(root) -> dict:
    live, rec = _paths(root)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    damaged, fresh = rec / f"kernel-{stamp}.damaged.sqlite3", rec / "salvaged.sqlite3"
    shutil.copy2(live, damaged)
    for suffix in ("-wal", "-shm"):
        side = live.parent / (live.name + suffix)
        if side.is_file():
            shutil.copy2(side, rec / (damaged.name + suffix))
    if fresh.exists():
        fresh.unlink()
    src = sqlite3.connect(damaged.as_uri() + "?mode=ro", uri=True, timeout=10)
    dst = sqlite3.connect(fresh)
    report = {"damaged_copy": damaged.name, "tables": {}, "schema_errors": []}
    try:
        objects = src.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
    except sqlite3.DatabaseError as exc:
        return {**report, "status": "SCHEMA_UNREADABLE", "error": str(exc)[:200]}
    for kind, name, sql in objects:
        if kind == "table":
            try:
                dst.execute(sql)
                report["tables"][name] = _copy_table(src, dst, name)
                dst.commit()
            except sqlite3.Error as exc:
                report["schema_errors"].append(f"{name}: {str(exc)[:80]}")
    for kind, name, sql in objects:
        if kind != "table":
            try:
                dst.execute(sql)
            except sqlite3.Error as exc:
                report["schema_errors"].append(f"{kind} {name}: {str(exc)[:80]}")
    try:
        version = src.execute("PRAGMA user_version").fetchone()[0]
        dst.execute(f"PRAGMA user_version={int(version)}")
    except sqlite3.Error:
        pass
    dst.commit()
    dst.execute("PRAGMA journal_mode=WAL")
    report["integrity"] = dst.execute("PRAGMA integrity_check").fetchone()[0]
    dst.close()
    src.close()
    os.chmod(fresh, 0o600)
    report["status"] = "SALVAGED" if report["integrity"] == "ok" else "SALVAGE_FAILED"
    return report


def swap(root) -> dict:
    live, rec = _paths(root)
    fresh = rec / "salvaged.sqlite3"
    if not fresh.is_file():
        return {"status": "NO_SALVAGE"}
    check = sqlite3.connect(fresh)
    ok = check.execute("PRAGMA integrity_check").fetchone()[0]
    check.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    check.close()
    if ok != "ok":
        return {"status": "REFUSED", "integrity": ok}
    for suffix in ("-wal", "-shm"):
        side = live.parent / (live.name + suffix)
        if side.is_file():
            side.unlink()                                          # copies are already in runtime/recovery
        extra = rec / (fresh.name + suffix)
        if extra.is_file():
            extra.unlink()
    os.replace(fresh, live)
    return {"status": "SWAPPED"}
