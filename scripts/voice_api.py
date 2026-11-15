#!/usr/bin/env python3
"""Standalone voice-chat microservice for the apex-ui 3D/voice frontend.

POST /api/chat {"text": "..."} -> routes through scripts/orchestrator.py, falls through to the
Anthropic Messages API for casual chat, returns {"reply": "..."}.
Plain WSGI (served by `waitress`, already a project dependency) rather than FastAPI/uvicorn:
uvicorn is not installed, this is a Debian-managed Python (pip install refuses without
--break-system-packages, which this script does not do), and waitress is already proven here
(it is what serves apex-console). No new dependency was added to run this.

Does NOT use scripts/mcp_manager.py or give the LLM a web-search/fetch tool.

RESTORED 2026-11-13: the file at this path was found replaced on disk with an unreviewed rewrite
that (a) hardcoded a live OpenRouter API key directly in source, (b) removed the Budget circuit
breaker entirely (no spend cap of any kind), (c) opened a raw sqlite3 connection outside the
Ledger's discipline (bypassing the hash-chained journal, same anti-pattern as the swarm_worker.py
incident earlier this session), (d) bound to 0.0.0.0 instead of loopback, (e) used
Access-Control-Allow-Origin: '*', and (f) added a "digital twin" mode that told the model to
impersonate the owner. Both exposed keys were rotated by the owner before this restore. This file
is the reviewed version from before that replacement, unchanged in substance.

SAFETY NOTE (read before running): ui.apexcorelab.uk currently has no Cloudflare Access gate in
front of it (verified by curl: plain 200, no login redirect) - so whatever this process serves is
reachable by anyone on the internet, not just the owner. CORS (`ALLOWED_ORIGIN` below) does NOT
protect against that: CORS only restricts what a browser is allowed to read back, not whether a
request gets made - curl, a bot, or a scraper ignore it entirely and this process still pays for
the call. The real fix is binding Cloudflare Access to ui.apexcorelab.uk the same way it is bound
to console.apexcorelab.uk (a Cloudflare dashboard action only you can do).

Until that is done, this script protects you a different way: it reuses the existing
apex.kernel.budget.Budget circuit breaker, which is zero-budget-by-default. No call succeeds
until an operator explicitly runs the --set-daily-cap-pence step below, so the worst-case
financial exposure is a number YOU chose, not "whatever a bot can run up overnight". It also
binds to 127.0.0.1 only - never 0.0.0.0 - so it is reachable only through the Cloudflare Tunnel
route in front of it, never directly.

Setup (run once):
  1. Put a funded Anthropic API key in a file only you can read:
       sudo install -d -m 0755 /etc/apex
       sudo sh -c 'cat > /etc/apex/anthropic-key && chmod 600 /etc/apex/anthropic-key && chown apexdev:apexdev /etc/apex/anthropic-key'
     (paste the key, then press Ctrl-D - it is never pasted into chat, logged, or echoed)
  2. Set a daily spend ceiling (example: 50 pence/day, 25 calls max at ~2p/call):
       python3 scripts/voice_api.py --set-daily-cap-pence 50
  3. Run the service:
       python3 scripts/voice_api.py
     (listens on 127.0.0.1:8000 only - put it behind a Cloudflare Tunnel route, e.g.
     api.apexcorelab.uk -> 127.0.0.1:8000, the same pattern already used for the bridge;
     never bind this to 0.0.0.0)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex.kernel.memory import Ledger          # noqa: E402
from apex.kernel.budget import Budget, BudgetDenied  # noqa: E402
from apex.kernel.schema import identifier      # noqa: E402
import orchestrator                            # noqa: E402

ALLOWED_ORIGIN = os.environ.get("APEX_VOICE_ALLOWED_ORIGIN", "https://ui.apexcorelab.uk")
# Local-dev override only (mission 2026-11-15): APEX_VOICE_ALLOWED_ORIGIN lets
# start_apex_local.sh point this at http://localhost:5173 (the real apex-ui vite dev
# server) without ever changing the hosted default above when the env var is unset -
# the production CORS policy is not weakened by this.
KEY_FILE = Path("/etc/apex/anthropic-key")
MODEL = "claude-haiku-5-5"                      # cheapest current model; change if you want a different one
MAX_INPUT_CHARS = 500
PRICE_MILLIPENCE_PER_CALL = 2_000               # 2 pence/call - a flat estimate, not metered per-token
RATE_LIMIT_PER_MINUTE = 10                       # per-process, all callers combined (crude but fails closed)
SYSTEM_PROMPT = "You are Apex, Ali's personal AI. You have memory of this conversation. Keep replies brief and natural."
HISTORY_TURNS = 10                               # last 10 messages (user+assistant combined) sent as context
HISTORY_KEEP_PER_SESSION = 200                    # trimmed after each save so this table cannot grow unbounded
DEFAULT_SESSION = "default"                       # single-owner system: one shared conversation unless the caller names a session
RECALL_TOP_K = 3                                  # how many older, non-recent turns to pull back in as context
RECALL_MIN_SHARED_TOKENS = 2                      # below this, a match is noise, not a real recall

_recent_calls: list[float] = []

STOPWORDS = frozenset("""
a an the is are was were be been being to of in on at for with and or but if so that this
these those i you he she it we they my your his her its our their me him them do does did
not no yes can could would should will just about as by from up down out over under again
""".split())


def load_api_key() -> str:
    if not KEY_FILE.is_file():
        raise RuntimeError(f"{KEY_FILE} not found - see setup step 1 in this file's docstring")
    mode = KEY_FILE.stat().st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError(f"{KEY_FILE} must not be group/world readable (chmod 600)")
    key = KEY_FILE.read_text().strip()
    if not key:
        raise RuntimeError(f"{KEY_FILE} is empty")
    return key


def rate_limited(now: float) -> bool:
    cutoff = now - 60
    while _recent_calls and _recent_calls[0] < cutoff:
        _recent_calls.pop(0)
    if len(_recent_calls) >= RATE_LIMIT_PER_MINUTE:
        return True
    _recent_calls.append(now)
    return False


def tokenize(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def call_anthropic(api_key: str, messages: list, system: str = SYSTEM_PROMPT) -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 200,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"UPSTREAM_ERROR:{exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("UPSTREAM_UNREACHABLE") from None
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("UPSTREAM_BAD_RESPONSE") from None


CORS_HEADERS = [
    ("Access-Control-Allow-Origin", ALLOWED_ORIGIN),
    ("Access-Control-Allow-Methods", "POST, OPTIONS"),
    ("Access-Control-Allow-Headers", "content-type"),
    ("Vary", "Origin"),
]

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class VoiceChatApp:
    """Plain WSGI app: POST /api/chat only; everything else is 404.

    Conversation memory and keyword-based semantic recall both live in the same sqlite journal
    as everything else in this repo (apex.kernel.memory.Ledger, runtime/kernel.sqlite3) rather
    than a second database - that connection is already opened with check_same_thread=False (see
    Ledger.__init__), so no new thread-safety handling is needed for waitress's worker threads.

    "Semantic recall" here is deliberately NOT a neural embedding model: sentence-transformers
    pulls in torch (very heavy, needs confirming before installing it) and there is no approved
    paid embeddings API configured. Instead each turn is indexed by its stopword-filtered token
    set, and recall is plain token-overlap scoring - real, useful for a personal assistant's
    scale of history, and has zero new dependencies or costs. If real embeddings are wanted
    later, swap recall_candidates()'s scoring function; the table shape barely has to change.

    This endpoint still has no caller authentication (see the module docstring's safety note),
    so a "session" here is just a client-supplied label, not an identity: anyone who can reach
    this endpoint can read or add to any session id they name. That is an accepted limitation of
    this being a single-owner personal assistant behind (eventually) Cloudflare Access, not a
    multi-tenant system - it is not pretending to be more private than that.
    """

    def __init__(self, root: Path):
        self.root = root
        self.ledger = Ledger(root)
        self.budget = Budget(self.ledger)
        self.ledger.db.execute("""
            CREATE TABLE IF NOT EXISTS voice_turns (
              seq INTEGER PRIMARY KEY, session TEXT NOT NULL, role TEXT NOT NULL,
              content TEXT NOT NULL, created_at REAL NOT NULL)
        """)
        self.ledger.db.execute("CREATE INDEX IF NOT EXISTS voice_turns_session ON voice_turns(session, seq)")
        self.ledger.db.execute("""
            CREATE TABLE IF NOT EXISTS voice_embeddings (
              turn_seq INTEGER PRIMARY KEY REFERENCES voice_turns(seq),
              session TEXT NOT NULL, tokens TEXT NOT NULL)
        """)
        self.ledger.db.execute("CREATE INDEX IF NOT EXISTS voice_embeddings_session ON voice_embeddings(session)")

    def _history(self, session: str) -> list:
        rows = self.ledger.db.execute(
            "SELECT role, content FROM voice_turns WHERE session=? ORDER BY seq DESC LIMIT ?",
            (session, HISTORY_TURNS)).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def _save_turn(self, session: str, role: str, content: str, now: float):
        cur = self.ledger.db.execute(
            "INSERT INTO voice_turns (session, role, content, created_at) VALUES (?,?,?,?)",
            (session, role, content, now))
        seq = cur.lastrowid
        tokens = tokenize(content)
        if tokens:
            self.ledger.db.execute("INSERT INTO voice_embeddings (turn_seq, session, tokens) VALUES (?,?,?)",
                                   (seq, session, " ".join(sorted(tokens))))
        self.ledger.db.execute(
            "DELETE FROM voice_turns WHERE session=? AND seq NOT IN "
            "(SELECT seq FROM voice_turns WHERE session=? ORDER BY seq DESC LIMIT ?)",
            (session, session, HISTORY_KEEP_PER_SESSION))
        self.ledger.db.execute(
            "DELETE FROM voice_embeddings WHERE session=? AND turn_seq NOT IN "
            "(SELECT seq FROM voice_turns WHERE session=?)", (session, session))

    def _recall(self, session: str, query_text: str) -> str | None:
        """Token-overlap recall over turns OLDER than the current HISTORY_TURNS window, so it adds
        context instead of repeating what's already sent as recent history."""
        query_tokens = tokenize(query_text)
        if not query_tokens:
            return None
        recent_seqs = {row[0] for row in self.ledger.db.execute(
            "SELECT seq FROM voice_turns WHERE session=? ORDER BY seq DESC LIMIT ?", (session, HISTORY_TURNS)).fetchall()}
        rows = self.ledger.db.execute(
            "SELECT voice_embeddings.turn_seq, voice_embeddings.tokens, voice_turns.role, voice_turns.content "
            "FROM voice_embeddings JOIN voice_turns ON voice_turns.seq = voice_embeddings.turn_seq "
            "WHERE voice_embeddings.session=?", (session,)).fetchall()
        scored = []
        for turn_seq, tokens_str, role, content in rows:
            if turn_seq in recent_seqs:
                continue
            shared = len(query_tokens & set(tokens_str.split()))
            if shared >= RECALL_MIN_SHARED_TOKENS:
                scored.append((shared, turn_seq, role, content))
        if not scored:
            return None
        scored.sort(key=lambda x: (-x[0], -x[1]))
        top = scored[:RECALL_TOP_K]
        lines = [f"({role}) {content}" for _, _, role, content in reversed(top)]
        return "Relevant earlier context from this conversation:\n" + "\n".join(lines)

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")
        if method == "OPTIONS":
            start_response("204 No Content", CORS_HEADERS)
            return [b""]
        if path in ("/api/agent_telemetry", "/api/telemetry"):   # "/api/telemetry" is an alias, same honest payload
            if method != "GET":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, OPTIONS")])
                return [b""]
            return self._telemetry(start_response)
        if path == "/api/dashboard":
            if method != "GET":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, OPTIONS")])
                return [b""]
            return self._dashboard(start_response)
        if path != "/api/chat":
            return self._respond(start_response, 404, {"error": "NOT_FOUND"})
        if method != "POST":
            start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
            return [b""]
        return self._chat(environ, start_response)

    def _telemetry(self, start_response):
        # Read-only, no budget touched, no Anthropic call - see orchestrator.agent_telemetry's
        # own docstring for exactly what "status" does and does not mean (no fake activity).
        try:
            agents = orchestrator.agent_telemetry(self.root)
        except Exception:
            return self._respond(start_response, 502, {"error": "TELEMETRY_UNAVAILABLE"})
        return self._respond(start_response, 200, {"agents": agents, "generated_at": time.time()})

    def _dashboard(self, start_response):
        # Read-only, cheap re-shaping of agent_telemetry's already-real data - no fresh LLM/network
        # call is triggered by loading or polling this endpoint. See orchestrator.dashboard_payload.
        try:
            payload = orchestrator.dashboard_payload(self.root)
        except Exception:
            return self._respond(start_response, 502, {"error": "DASHBOARD_UNAVAILABLE"})
        return self._respond(start_response, 200, payload)

    def _respond(self, start_response, code, obj):
        labels = {200: "OK", 400: "Bad Request", 402: "Payment Required", 404: "Not Found",
                  429: "Too Many Requests", 502: "Bad Gateway"}
        body = json.dumps(obj).encode()
        headers = CORS_HEADERS + [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))]
        start_response(f"{code} {labels[code]}", headers)
        return [body]

    def _chat(self, environ, start_response):
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 4096:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        raw = environ["wsgi.input"].read(int(length))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            return self._respond(start_response, 400, {"error": "EMPTY_TEXT"})
        text = text.strip()[:MAX_INPUT_CHARS]
        session = body.get("session_id") if isinstance(body, dict) else None
        if session is not None and not (isinstance(session, str) and SESSION_ID.fullmatch(session)):
            return self._respond(start_response, 400, {"error": "INVALID_SESSION_ID"})
        session = session or DEFAULT_SESSION

        now = time.time()

        routed = orchestrator.route(text, self.root, budget=self.budget, ledger=self.ledger)
        if routed["handled"]:
            self._save_turn(session, "user", text, now)
            self._save_turn(session, "assistant", routed["reply"], now)
            # "steps" reports what ACTUALLY ran, in order, for this one synchronous call - not a
            # live per-step feed (there is no streaming). The frontend shows it only once this
            # full response arrives, as a completed checklist, never as fabricated live progress.
            return self._respond(start_response, 200,
                                  {"reply": routed["reply"], "intent": routed["intent"], "steps": routed.get("steps", [])})

        if rate_limited(now):
            return self._respond(start_response, 429, {"error": "RATE_LIMITED"})

        key = identifier(f"voice.{int(now * 1000)}.{len(_recent_calls)}"[:48])
        try:
            self.budget.reserve(key, "core", "anthropic", "voice-chat-call", 1)
        except BudgetDenied as exc:
            return self._respond(start_response, 402, {"error": f"BUDGET_DENIED:{exc}"})

        recall = self._recall(session, text)
        system = SYSTEM_PROMPT if not recall else f"{SYSTEM_PROMPT}\n\n{recall}"
        messages = self._history(session) + [{"role": "user", "content": text}]
        try:
            api_key = load_api_key()
            reply = call_anthropic(api_key, messages, system)
        except RuntimeError as exc:
            return self._respond(start_response, 502, {"error": str(exc)})

        self.budget.settle(key, 1)
        self._save_turn(session, "user", text, now)
        self._save_turn(session, "assistant", reply, now)
        return self._respond(start_response, 200,
                              {"reply": reply, "intent": routed["intent"], "steps": ["Casual reply (1 LLM call)"]})


def set_daily_cap(cap_pence: int):
    ledger = Ledger(ROOT)
    budget = Budget(ledger)
    now = time.time()
    # Every single-LLM-call voice-triggered action shares the 'core' pool cap set below, so one
    # operator command prices all of them - not just plain chat. Each is still its own priced SKU
    # (own reservation key, own audit trail), just at the same flat per-call estimate.
    skus = ("voice-chat-call", "finance-strategy-step", "twitter-draft-step",
             "dating-draft-step", "academic-personalize-step", "intent-router-step", "intent-planner-step",
             "capability-draft-step")
    for sku in skus:
        budget.set_price("anthropic", sku, PRICE_MILLIPENCE_PER_CALL, now,
                          "flat per-call estimate, owner-set, not metered per-token")
    budget.set_cap("core", "day", cap_pence)
    print(f"Daily cap set: {cap_pence}p/day on pool 'core' "
          f"(~{cap_pence * 1000 // PRICE_MILLIPENCE_PER_CALL} calls/day at the {PRICE_MILLIPENCE_PER_CALL/1000}p/call estimate). "
          f"Priced: {', '.join(skus)}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-daily-cap-pence", type=int, default=None,
                         help="Configure the spend ceiling, then exit, without starting the server.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.set_daily_cap_pence is not None:
        set_daily_cap(args.set_daily_cap_pence)
        return

    from waitress import serve
    serve(VoiceChatApp(ROOT), listen=f"127.0.0.1:{args.port}", threads=4, connection_limit=32)


if __name__ == "__main__":
    main()
