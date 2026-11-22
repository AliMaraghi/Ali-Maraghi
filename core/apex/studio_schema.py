"""Studio tables in the existing SQLite file. apply() first takes and checks a full backup, then creates only what is
missing; rollback() drops exactly these tables. It never creates a database: a missing file is an error."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

VERSION = 1
TABLES = {
    "studio_global_sources": "source_id TEXT PRIMARY KEY, family TEXT NOT NULL, market TEXT NOT NULL, language TEXT NOT NULL, url TEXT NOT NULL, last_ok REAL, last_error TEXT, failures INTEGER NOT NULL DEFAULT 0",
    "studio_global_research_runs": "run_id TEXT PRIMARY KEY, started_at REAL NOT NULL, finished_at REAL, sources_ok INTEGER, sources_failed INTEGER, observations INTEGER, errors TEXT",
    "studio_global_topics": "topic_id TEXT PRIMARY KEY, label TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL, markets TEXT, languages TEXT, score REAL, score_version TEXT, velocity TEXT",
    "studio_global_trend_observations": "id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, source_id TEXT NOT NULL, topic_id TEXT NOT NULL, original_title TEXT NOT NULL, language TEXT NOT NULL, market TEXT NOT NULL, source_url TEXT NOT NULL, source_family TEXT NOT NULL, observed_at REAL NOT NULL, published_at REAL, metric_name TEXT NOT NULL, metric_value REAL, measurement_window TEXT, UNIQUE(run_id, source_id, topic_id)",
    "studio_global_topic_evidence": "topic_id TEXT NOT NULL, headline_hash TEXT NOT NULL, headline TEXT NOT NULL, market TEXT NOT NULL, first_seen REAL NOT NULL, PRIMARY KEY (topic_id, headline_hash)",
    "studio_content_localizations": "job_id TEXT NOT NULL, language TEXT NOT NULL, state TEXT NOT NULL, artifact TEXT, created_at REAL NOT NULL, PRIMARY KEY (job_id, language)",
    "studio_comment_inbox": "platform TEXT NOT NULL, account TEXT NOT NULL, post_id TEXT NOT NULL, comment_id TEXT NOT NULL, text TEXT NOT NULL, language TEXT, language_confidence REAL, classification TEXT, received_via TEXT NOT NULL, received_at REAL NOT NULL, PRIMARY KEY (platform, account, post_id, comment_id)",
    "studio_reply_outbox": "platform TEXT NOT NULL, account TEXT NOT NULL, post_id TEXT NOT NULL, comment_id TEXT NOT NULL, reply TEXT NOT NULL, reply_hash TEXT NOT NULL, state TEXT NOT NULL, due_at REAL NOT NULL, remote_id TEXT, policy_version TEXT, model TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL, PRIMARY KEY (platform, account, post_id, comment_id)",
    "studio_reply_rate_reservations": "id INTEGER PRIMARY KEY, platform TEXT NOT NULL, account TEXT NOT NULL, comment_id TEXT NOT NULL, reserved_at REAL NOT NULL, UNIQUE(platform, account, comment_id)",
    "studio_webhook_receipts": "provider TEXT NOT NULL, delivery_id TEXT NOT NULL, received_at REAL NOT NULL, body_hash TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY (provider, delivery_id)",
}


def missing(db_path) -> list:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        have = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        db.close()
    return [t for t in TABLES if t not in have]


def apply(db_path, backup_dir, now: float | None = None) -> dict:
    db_path, now = Path(db_path), time.time() if now is None else now
    if not db_path.is_file():
        raise FileNotFoundError("database not found; refusing to create one")
    todo = missing(db_path)
    if not todo:
        return {"applied": [], "backup": None, "version": VERSION}
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"kernel-before-studio-v{VERSION}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime(now))}.sqlite3"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(str(backup))
    try:
        src.backup(dst)
        tables_src = src.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and dst.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == tables_src
    finally:
        src.close()
        dst.close()
    __import__("os").chmod(backup, 0o600)
    if not ok:
        raise RuntimeError("backup did not verify; nothing was changed")
    db = sqlite3.connect(str(db_path), timeout=30)
    try:
        with db:                                                   # one short transaction: all tables or none
            for name in todo:
                db.execute(f"CREATE TABLE IF NOT EXISTS {name} ({TABLES[name]})")
    finally:
        db.close()
    return {"applied": todo, "backup": backup.name, "version": VERSION}


def rollback(db_path) -> list:
    db = sqlite3.connect(str(db_path), timeout=30)
    try:
        with db:
            for name in TABLES:
                db.execute(f"DROP TABLE IF EXISTS {name}")
    finally:
        db.close()
    return list(TABLES)
