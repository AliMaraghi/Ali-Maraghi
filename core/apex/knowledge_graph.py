"""Knowledge graph in its own small SQLite file (runtime/graph.sqlite3, WAL): entities and edges rebuilt from what the
server really holds - LinkedIn connections, companies, job listings, picked events, trends and property boroughs.
links() surfaces cross-source connections (e.g. a listing at a company where the owner knows people)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


def _norm(text: str) -> str:
    return " ".join(re.sub(r"\b(ltd|limited|plc|inc|llc|group|uk)\b|[^a-z0-9 ]", " ", str(text).lower()).split())


def _open(root):
    db = sqlite3.connect(Path(root) / "runtime" / "graph.sqlite3", timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""CREATE TABLE IF NOT EXISTS entities (id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, data TEXT);
                        CREATE TABLE IF NOT EXISTS edges (src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL, PRIMARY KEY (src, rel, dst));""")
    return db


def rebuild(root, people: list, jobs: list, events: list, trends: list, boroughs: list) -> dict:
    ents, edges = {}, set()
    def ent(kind, label, data=None):
        key = f"{kind}:{_norm(label)}"[:160]
        if _norm(label):
            ents.setdefault(key, (kind, str(label)[:160], json.dumps(data) if data else None))
            return key
    for p in people:
        a, c = ent("person", p.get("name", ""), {"position": p.get("position")}), ent("company", p.get("company", ""))
        if a and c:
            edges.add((a, "works_at", c))
    for j in jobs:
        a, c = ent("job", f"{j.get('title')} @ {j.get('company')}", {"url": j.get("url")}), ent("company", j.get("company", ""))
        if a and c:
            edges.add((a, "offered_by", c))
    for e in events:
        ent("event", e.get("title", ""), {"start": e.get("start"), "url": e.get("url")})
    for t in trends:
        a = ent("trend", t.get("term", ""), {"score": t.get("score")})
        for g in t.get("geos") or []:
            b = ent("market", g)
            if a and b:
                edges.add((a, "trending_in", b))
    for b in boroughs:
        ent("area", b.get("borough", ""), {"terraced": b.get("terraced"), "within_budget": b.get("terraced_within_budget")})
    db = _open(root)
    with db:
        db.execute("DELETE FROM entities")
        db.execute("DELETE FROM edges")
        db.executemany("INSERT INTO entities VALUES (?,?,?,?)", [(k, *v) for k, v in ents.items()])
        db.executemany("INSERT OR IGNORE INTO edges VALUES (?,?,?)", list(edges))
    out = {"entities": len(ents), "edges": len(edges),
           "by_kind": dict(db.execute("SELECT kind, COUNT(*) FROM entities GROUP BY kind").fetchall()), "links": links(db)}
    db.close()
    return out


def links(db) -> list:
    """Cross-source links: a job at a company where the owner already knows someone."""
    rows = db.execute("""SELECT j.label, c.label, GROUP_CONCAT(p.label, '; ') FROM edges ej
                         JOIN entities j ON j.id = ej.src AND ej.rel = 'offered_by'
                         JOIN entities c ON c.id = ej.dst
                         JOIN edges ep ON ep.dst = c.id AND ep.rel = 'works_at'
                         JOIN entities p ON p.id = ep.src GROUP BY j.id LIMIT 15""").fetchall()
    return [{"job": r[0], "company": r[1], "you_know": r[2][:300]} for r in rows]
