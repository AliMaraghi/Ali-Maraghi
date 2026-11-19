"""People graph from the owner's own LinkedIn export (Connections.csv): who he knows, where they work, since when.
Stored privately on the server (runtime/inbox/people.json, mode 0600), never committed, no e-mail addresses kept.
Links to the job agent: listings at companies where he already knows someone are flagged."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from pathlib import Path

MAX_PEOPLE = 5000


def _path(root) -> Path:
    return Path(root) / "runtime" / "inbox" / "people.json"


def _norm(company: str) -> str:
    return re.sub(r"\b(ltd|limited|plc|inc|llc|group|uk)\b|[^a-z0-9 ]", " ", company.lower()).split() and " ".join(
        re.sub(r"\b(ltd|limited|plc|inc|llc|group|uk)\b|[^a-z0-9 ]", " ", company.lower()).split()) or ""


def parse(csv_text: str) -> list:
    lines = csv_text.replace("\r\n", "\n").split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("First Name,")), None)
    if start is None:
        raise ValueError("not a LinkedIn Connections export")
    people = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        name = f"{(row.get('First Name') or '').strip()} {(row.get('Last Name') or '').strip()}".strip()[:80]
        if name:
            year = (re.search(r"(\d{4})\s*$", row.get("Connected On") or "") or [None, None])[1]
            people.append({"name": name, "company": (row.get("Company") or "").strip()[:100],
                           "position": (row.get("Position") or "").strip()[:120], "year": year})
    return people[:MAX_PEOPLE]


def save(root, people: list) -> int:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump({"source": "linkedin", "people": people}, out)
    return len(people)


def load(root) -> list:
    try:
        return json.loads(_path(root).read_text(encoding="utf-8")).get("people") or []
    except (OSError, ValueError, AttributeError):
        return []


def summary(root) -> dict | None:
    people = load(root)
    if not people:
        return None
    companies = Counter(p["company"] for p in people if p["company"])
    words = Counter(w for p in people for w in re.findall(r"[a-z]{4,}", p["position"].lower())
                    if w not in {"manager", "senior", "head", "lead", "with", "and"})
    by_co: dict = {}
    for p in people:
        if p["company"]:
            by_co.setdefault(_norm(p["company"]), []).append(p)
    warm = []
    try:
        jobs = json.loads((Path(root) / "runtime" / "inbox" / "jobs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        jobs = []
    seen = set()
    for job in jobs if isinstance(jobs, list) else []:
        key = _norm(str(job.get("company", ""))) if isinstance(job, dict) else ""
        if key and key in by_co and (key, job.get("title")) not in seen:
            seen.add((key, job.get("title")))
            warm.append({"title": job.get("title"), "company": job.get("company"), "url": job.get("url"),
                         "you_know": [f"{p['name']} ({p['position']})" for p in by_co[key][:3]]})
    return {"people": len(people), "companies": len(companies), "top_companies": companies.most_common(8),
            "top_role_words": words.most_common(8), "by_year": sorted(Counter(p["year"] for p in people if p["year"]).items()),
            "warm_jobs": warm[:10]}
