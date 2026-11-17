"""Semantic memory: embeddings of what the owner said, stored in the existing SQLite file.

One table (memory_items) holds the text and its embedding. If the sqlite-vec extension can be
loaded, a vec0 index (memory_vec_<dim>) answers nearest-neighbour queries; if it cannot (no
pip on the host, or a Python built without extension loading) the same query runs as an exact
cosine scan in Python. At a single owner's scale (tens of thousands of items) both are fast;
results are the same either way, so sqlite-vec is an accelerator here, not a requirement.

What goes in: conversation turns, daily briefings, notes. What does NOT go in: bank
transactions - numbers do not embed meaningfully and sums must be exact, so those stay as
structured rows queried by the statement tools.

Embeddings come from the injected `embed` callable (apex.local_llm.embed - a local model).
Nothing in this module makes a network call of its own.
"""
from __future__ import annotations

import math
import sqlite3
import struct
import time
from typing import Callable

MAX_TEXT_CHARS = 4000


def _pack(vector) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack(blob: bytes) -> tuple:
    return struct.unpack(f"{len(blob) // 4}f", blob)


def _normalise(vector) -> list:
    norm = math.sqrt(sum(x * x for x in vector))
    if not norm or not math.isfinite(norm):
        raise ValueError("Embedding has no direction")
    return [x / norm for x in vector]


class SemanticMemory:
    def __init__(self, db: sqlite3.Connection, embed: Callable[[list], list], clock=time.time):
        self.db, self.embed, self.clock = db, embed, clock
        self.vec = self._load_sqlite_vec()
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory_items (
              id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL, text TEXT NOT NULL,
              created_at REAL NOT NULL, dim INTEGER NOT NULL, embedding BLOB NOT NULL,
              UNIQUE(kind, ref))
        """)
        db.execute("CREATE INDEX IF NOT EXISTS memory_items_kind ON memory_items(kind)")

    def _load_sqlite_vec(self) -> bool:
        try:
            import sqlite_vec
            self.db.enable_load_extension(True)
            try:
                sqlite_vec.load(self.db)
            finally:
                self.db.enable_load_extension(False)
            self.db.execute("SELECT vec_version()").fetchone()
            return True
        except Exception:
            return False

    @property
    def backend(self) -> str:
        return "sqlite-vec" if self.vec else "python-scan"

    def _index(self, dim: int) -> str:
        name = f"memory_vec_{int(dim)}"
        self.db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING vec0("
                        f"embedding float[{int(dim)}] distance_metric=cosine)")
        return name

    # ---- write -------------------------------------------------------------
    def add(self, kind: str, ref: str, text: str) -> int | None:
        """Embed and store one item. Same (kind, ref) replaces the earlier text."""
        text = (text or "").strip()[:MAX_TEXT_CHARS]
        if not text or not kind or not ref:
            return None
        vector = _normalise(self.embed([text])[0])
        self.forget(kind, ref)
        cur = self.db.execute(
            "INSERT INTO memory_items (kind, ref, text, created_at, dim, embedding) VALUES (?,?,?,?,?,?)",
            (kind, ref, text, self.clock(), len(vector), _pack(vector)))
        if self.vec:
            self.db.execute(f"INSERT INTO {self._index(len(vector))}(rowid, embedding) VALUES (?,?)",
                            (cur.lastrowid, _pack(vector)))
        return cur.lastrowid

    def forget(self, kind: str, ref: str) -> bool:
        row = self.db.execute("SELECT id, dim FROM memory_items WHERE kind=? AND ref=?", (kind, ref)).fetchone()
        if row is None:
            return False
        if self.vec:
            self.db.execute(f"DELETE FROM {self._index(row[1])} WHERE rowid=?", (row[0],))
        self.db.execute("DELETE FROM memory_items WHERE id=?", (row[0],))
        return True

    def count(self, kind: str | None = None) -> int:
        if kind:
            return self.db.execute("SELECT COUNT(*) FROM memory_items WHERE kind=?", (kind,)).fetchone()[0]
        return self.db.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]

    # ---- read --------------------------------------------------------------
    def search(self, query: str, k: int = 3, kinds: tuple | None = None, ref_prefix: str | None = None,
               exclude_refs: set | None = None, min_score: float = 0.35) -> list:
        """Top-k items by cosine similarity. Returns [{"kind","ref","text","score","created_at"}]."""
        query = (query or "").strip()
        if not query or k < 1:
            return []
        vector = _normalise(self.embed([query[:MAX_TEXT_CHARS]])[0])
        dim, exclude = len(vector), exclude_refs or set()

        def keep(kind, ref):
            return ((not kinds or kind in kinds) and (not ref_prefix or ref.startswith(ref_prefix))
                    and ref not in exclude)

        scored = []
        if self.vec:
            # vec0 fixes its k nearest before any other filter applies, so over-fetch and filter here.
            fetch = min(max(k * 8, 40), 400)
            near = self.db.execute(
                f"SELECT rowid, distance FROM {self._index(dim)} WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (_pack(vector), fetch)).fetchall()
            for rowid, distance in near:
                row = self.db.execute("SELECT kind, ref, text, created_at FROM memory_items WHERE id=?",
                                      (rowid,)).fetchone()
                if row and keep(row[0], row[1]):
                    scored.append((1.0 - distance, row))
        else:
            for kind, ref, text, created_at, blob in self.db.execute(
                    "SELECT kind, ref, text, created_at, embedding FROM memory_items WHERE dim=?", (dim,)):
                if keep(kind, ref):
                    scored.append((sum(a * b for a, b in zip(vector, _unpack(blob))), (kind, ref, text, created_at)))
            scored.sort(key=lambda item: item[0], reverse=True)
        return [{"kind": row[0], "ref": row[1], "text": row[2], "created_at": row[3], "score": round(score, 4)}
                for score, row in scored if score >= min_score][:k]


def open_if_enabled(db: sqlite3.Connection):
    """A SemanticMemory bound to the local embedding model, or None when the local provider is off
    (so the hosted configuration keeps its existing keyword recall and makes no embedding calls)."""
    from . import local_llm
    if not local_llm.enabled():
        return None
    return SemanticMemory(db, local_llm.embed)
