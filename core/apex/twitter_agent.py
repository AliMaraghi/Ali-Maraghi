"""A-20 Twitter/X: read mentions, draft a reply with the budget-gated LLM, save the draft to the
Ledger for review. Status: TESTS_NOT_RUN, NOT_CONNECTED.

Structurally cannot post: this module only ever calls GET (mentions) and the local save function;
there is no function anywhere in this file that performs a POST to /2/tweets or any write
endpoint. That is the same discipline core/apex/gmail_drafts.py already uses (a _GuardedTransport
that physically cannot reach any path but the one reviewed write target) - here it is simpler
still, because there is no reviewed write target at all yet.

Free-tier reality check (X API v2, checked 2026-11-13): the free tier only grants POST /2/tweets
and a few read-your-own-account endpoints; general search/trends (GET /2/tweets/search/recent,
GET /2/trends/by/woeid) need the paid Basic/Pro tiers. This module therefore reads
GET /2/users/:id/mentions (available on free tier with OAuth 2.0 user context) rather than
assuming trends access exists; if the owner's tier doesn't include it, the API returns 403/429
and this fails closed with that status, not a fabricated result.

Setup: create an app at developer.x.com, get an OAuth 2.0 user-context bearer token (or app-only
bearer token for mentions lookup, per your plan), and store it the same way the other per-service
tokens in this project are stored:
  sudo install -d -m 0755 /etc/apex
  sudo sh -c 'cat > /etc/apex/twitter-token.json && chmod 600 /etc/apex/twitter-token.json && chown apexdev:apexdev /etc/apex/twitter-token.json'
  (paste {"bearer_token": "...", "user_id": "..."} then Ctrl-D)
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .agents_research import call_anthropic, load_api_key, ResearchPipelineError
from .kernel.budget import Budget

HOST = "api.x.com"
LIMIT = 1_000_000
TOKEN_FILE = Path("/etc/apex/twitter-token.json")
MAX_DRAFT_CHARS = 280
TOKEN = re.compile(r"[A-Za-z0-9._~+/=%-]{20,8192}")
USER_ID = re.compile(r"[0-9]{1,32}")
PROVIDER, SKU = "anthropic", "twitter-draft-step"
TONE = ("Draft a short, respectful, specific reply to the mention below - under 280 characters, "
        "no hashtags unless the mention itself uses them, no promises on the owner's behalf. "
        "This is a DRAFT for the owner to edit and send themselves; never claim to have sent it.")


class TwitterAgentError(RuntimeError):
    pass


def load_credentials() -> dict:
    if not TOKEN_FILE.is_file():
        raise TwitterAgentError(f"{TOKEN_FILE} not found - see setup steps in this file's docstring")
    mode = TOKEN_FILE.stat().st_mode & 0o777
    if mode & 0o077:
        raise TwitterAgentError(f"{TOKEN_FILE} must not be group/world readable (chmod 600)")
    try:
        data = json.loads(TOKEN_FILE.read_text())
    except json.JSONDecodeError:
        raise TwitterAgentError("Invalid token file") from None
    token, user_id = data.get("bearer_token"), data.get("user_id")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise TwitterAgentError("Invalid bearer_token")
    if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id):
        raise TwitterAgentError("Invalid user_id")
    return {"bearer_token": token, "user_id": user_id}


def fetch_mentions(bearer_token: str, user_id: str, transport, max_results: int = 10) -> list:
    """GET /2/users/:id/mentions only. Returns a bounded list of {id, text}. 403/429 (tier limits
    or rate limiting) raise TwitterAgentError with the real status, never a fabricated empty-ok."""
    if not 5 <= max_results <= 20:
        raise ValueError("max_results out of bounds")
    path = f"/2/users/{user_id}/mentions?max_results={max_results}&tweet.fields=text"
    headers = {"Authorization": "Bearer " + bearer_token, "Accept": "application/json"}
    try:
        status, content_type, raw = transport("GET", path, headers)
    except Exception:
        raise TwitterAgentError("TRANSPORT_ERROR") from None
    if status != 200:
        raise TwitterAgentError(f"TWITTER_HTTP_{int(status)}")      # upstream body never surfaced/logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip().lower() != "application/json":
        raise TwitterAgentError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(raw.decode())
    except ValueError:
        raise TwitterAgentError("INVALID_RESPONSE") from None
    items = data.get("data") if isinstance(data, dict) else None
    if items is None:
        return []
    if not isinstance(items, list) or len(items) > max_results:
        raise TwitterAgentError("INVALID_RESPONSE")
    out = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("text"), str):
            raise TwitterAgentError("INVALID_RESPONSE")
        out.append({"id": item["id"][:64], "text": item["text"][:2000]})
    return out


def generate_and_save_draft(budget: Budget, ledger, mention_id: str, mention_text: str, run_id: str) -> int:
    """Budget-gated LLM call (reserve/settle, zero-budget-by-default - same pattern as A-2's
    _spend() in agents_research.py) producing ONE draft reply, saved locally via save_draft().
    Never calls any Twitter write endpoint - there is no such function in this module.

    Calibration (same pattern as orchestrator.py's finance_strategy_reply): before drafting,
    real past outcomes recorded against prior "twitter_draft_*" facts (via the existing, generic
    scripts/record_outcome.py - no new tool needed) are read and included in the prompt, so a
    past rejection visibly changes this draft. After drafting, the new draft is ALSO asserted as
    a fact (subject "owner", predicate "twitter_draft_<seq-to-be>") so the owner can record an
    outcome against it the same generic way."""
    from apex.kernel import facts
    key = f"{run_id}.draft"
    budget.reserve(key, "core", PROVIDER, SKU, 1)
    past_outcomes = facts.recent_outcomes_for_predicate_prefix(ledger, "owner", "twitter_draft_", limit=3)
    calibration_note = ""
    if past_outcomes:
        lines = [f"- a past draft was {o['outcome']}" + (f" ({o['note']})" if o["note"] else "") for o in past_outcomes]
        calibration_note = ("\n\nWhat happened to past drafts (recorded by the owner - let this "
                             "visibly change this draft, e.g. avoid repeating a rejected tone):\n" + "\n".join(lines))
    try:
        api_key = load_api_key()
        draft = call_anthropic(api_key, TONE, f"Mention: {mention_text}{calibration_note}", max_tokens=100)
    except ResearchPipelineError:
        budget.release(key)
        raise
    budget.settle(key, 1)
    seq = save_draft(ledger, mention_id, draft[:MAX_DRAFT_CHARS], time.time())
    facts.assert_fact(ledger, "owner", f"twitter_draft_{seq}", draft[:MAX_DRAFT_CHARS], "A-20:TwitterAgent")
    return seq


def save_draft(ledger, mention_id: str, draft_text: str, now: float) -> int:
    """Local record only - never dispatched anywhere. The owner reads/edits/sends it themselves."""
    if not isinstance(draft_text, str) or not 1 <= len(draft_text) <= MAX_DRAFT_CHARS:
        raise ValueError(f"Draft must be 1..{MAX_DRAFT_CHARS} chars (X's own limit)")
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS twitter_drafts (
          seq INTEGER PRIMARY KEY, mention_id TEXT NOT NULL, draft_text TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'DRAFT', created_at REAL NOT NULL)
    """)
    cur = ledger.db.execute(
        "INSERT INTO twitter_drafts (mention_id, draft_text, created_at) VALUES (?,?,?)",
        (mention_id, draft_text, now))
    return cur.lastrowid


def list_drafts(ledger) -> list:
    ledger.db.execute("""
        CREATE TABLE IF NOT EXISTS twitter_drafts (
          seq INTEGER PRIMARY KEY, mention_id TEXT NOT NULL, draft_text TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'DRAFT', created_at REAL NOT NULL)
    """)
    rows = ledger.db.execute(
        "SELECT seq, mention_id, draft_text, status, created_at FROM twitter_drafts ORDER BY seq DESC LIMIT 50")
    return [{"seq": r[0], "mention_id": r[1], "draft_text": r[2], "status": r[3], "created_at": r[4]}
            for r in rows]


def live_transport(method, path, headers):                      # pragma: no cover - not exercised offline
    if method != "GET":
        raise ValueError("Only GET is permitted - this module never posts")
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, None, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()
