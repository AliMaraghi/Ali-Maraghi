"""Shared pieces for the Opportunity Scouts (scout_events.py, scout_wealth.py).

Scouts are read-only background workers: they fetch public feeds through the reviewed
transport, let the model RANK or PHRASE what was fetched, and write the result to the Ledger
for the dashboard. They never act on anything, and nothing the model writes is shown unless
it survives the checks here (indices in range, no number that was not in the fetched data,
no buy/sell language).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from .kernel.budget import BudgetDenied

PROVIDER, POOL, SKU = "anthropic", "core", "scout-step"     # provider is only the reservation label
MAX_FEED_BYTES = 1_048_576
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
ADVICE = re.compile(r"\b(buy|sell|invest(?:ing)? in|you should|must|guaranteed)\b", re.I)
URLISH = re.compile(r"https?://\S+|www\.\S+", re.I)
DEFAULT_CONFIG = {
    # Who the events are being ranked for. Edit runtime/inbox/scout_config.json to change it;
    # that folder is never committed, so personal details stay out of the repository.
    "profile": "A London-based professional looking for good tech networking and well-run social events.",
    # Public London groups whose calendars answered on 2026-11-18 (tech/startup networking, then
    # social nights). Watching a group needs no membership; attending is the owner's own step.
    "meetup_groups": ["london-technology-community", "london-entrepreneur-startup-network-tech-business-ecommerce",
                      "london-new-tech", "TechSocialLondon", "disruptive-tech-lon", "speed-network-now",
                      "londonpartypeople", "london-night-out", "tastour", "bored-in-london", "singlesclublondon"],
    "event_keywords": ["singles", "mixer", "speed dating", "wine tasting", "gallery", "networking", "tech",
                       "social", "founders"],
    "food_weekly_cap_pence": 10_000,                     # the owner's weekly limit for food ordered in or eaten out
    "job_keywords": "procurement manager",
    "job_location": "London",
    "finance_keywords": ["FTSE", "interest rate", "inflation", "Bank of England", "pound", "gold",
                         "bitcoin", "mortgage", "ISA", "chip", "semiconductor"],
}


def load_config(root: Path) -> dict:
    config = dict(DEFAULT_CONFIG)
    path = Path(root) / "runtime" / "inbox" / "scout_config.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            for key, default in DEFAULT_CONFIG.items():
                if isinstance(data.get(key), type(default)):
                    config[key] = data[key]
    return config


def clean(text, limit: int) -> str:
    return " ".join(URLISH.sub("", str(text or "")).split())[:limit]


def parse_rss(raw: bytes, allowed_hosts: set, limit: int = 20) -> list:
    """[(title, link)] from an RSS 2.0 feed; links must be https on an allowed host."""
    if not isinstance(raw, bytes) or len(raw) > MAX_FEED_BYTES:
        raise ValueError("Feed too large")
    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Feed declarations are not permitted")
    out = []
    for item in ET.fromstring(raw).findall(".//item"):
        title = clean(item.findtext("title"), 300)
        link = (item.findtext("link") or "").strip()
        parsed = urlparse(link)
        if title and parsed.scheme == "https" and parsed.hostname in allowed_hosts and len(link) <= 500:
            out.append((title, link))
        if len(out) >= limit:
            break
    return out


def numbers_ok(text: str, source_text: str) -> bool:
    """True only if every number in `text` also appears in the data the model was given."""
    known = {n.replace(",", "") for n in NUMBER.findall(source_text)}
    return all(n.replace(",", "") in known for n in NUMBER.findall(text))


def ask_json(llm, budget, key: str, system: str, user_text: str, max_tokens: int = 300):
    """One budget-gated model call that must return a JSON object. None on any failure -
    callers always have a deterministic fallback, so a weak or absent model degrades the
    ranking, never the facts."""
    if llm is None or budget is None:
        return None, "no-model"
    try:
        budget.reserve(key, POOL, PROVIDER, SKU, 1)
    except BudgetDenied as exc:
        return None, f"budget:{exc}"
    try:
        raw = llm(system, user_text, max_tokens)
    except Exception as exc:
        try:
            budget.release(key)
        except Exception:
            pass
        return None, f"model:{type(exc).__name__}"
    budget.settle(key, 1)
    start, end = raw.find("{"), raw.rfind("}")
    try:
        obj = json.loads(raw[start:end + 1]) if 0 <= start < end else None
    except ValueError:
        obj = None
    return (obj, "ok") if isinstance(obj, dict) else (None, "invalid-json")


def record(ledger, name: str, payload: dict, now: float) -> str:
    key = f"scout.{name}." + time.strftime("%Y%m%d.%H%M%S", time.gmtime(now))
    ledger.append(key, "decision", "personal", {**payload, "generated_at": round(now, 3)})
    return key


def latest(root: Path, name: str) -> dict | None:
    """Most recent scout result, read-only, for the dashboard. None if it has never run."""
    path = Path(root) / "runtime" / "kernel.sqlite3"
    if not path.is_file():
        return None
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        row = db.execute("SELECT payload FROM events WHERE event_key LIKE ? AND kind='decision' "
                         "ORDER BY seq DESC LIMIT 1", (f"scout.{name}.%",)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        db.close()
    return json.loads(row[0]) if row else None
