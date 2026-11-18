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
from apex import local_llm, semantic_memory    # noqa: E402

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
BANKING_CSV_MAX_BODY_BYTES = 262_144              # ~256KB JSON body; banking_csv.py bounds the CSV itself further
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
    if local_llm.enabled():
        return "local"                     # local Ollama model: no hosted key is read or needed
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
    if local_llm.enabled():
        return local_llm.chat(system, messages, max_tokens=200)   # LocalLLMError is a RuntimeError -> 502
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
        # Real embeddings, only when the local provider is on (APEX_LLM_PROVIDER=ollama): stored
        # in this same SQLite file via sqlite-vec (or an exact Python scan if the extension is
        # absent). None otherwise - the hosted configuration keeps the keyword recall below.
        try:
            self.semantic = semantic_memory.open_if_enabled(self.ledger.db)
        except Exception:
            self.semantic = None

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
        if self.semantic is not None:
            try:                                   # long-term memory; never allowed to break a chat turn
                self.semantic.add("conversation", f"{session}:{seq}", f"({role}) {content}")
            except Exception:
                pass
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
        if self.semantic is not None:
            try:
                recent = {f"{session}:{row[0]}" for row in self.ledger.db.execute(
                    "SELECT seq FROM voice_turns WHERE session=? ORDER BY seq DESC LIMIT ?",
                    (session, HISTORY_TURNS)).fetchall()}
                hits = self.semantic.search(query_text, k=RECALL_TOP_K, kinds=("conversation", "briefing", "note"),
                                            exclude_refs=recent)
                if hits:
                    return "Relevant earlier context (from memory):\n" + "\n".join(h["text"][:600] for h in hits)
            except Exception:
                pass                               # fall through to keyword recall
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
        if path == "/api/academic/latest":
            if method != "GET":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, OPTIONS")])
                return [b""]
            return self._academic_latest(start_response, translate="translate=fa" in environ.get("QUERY_STRING", ""))
        if path == "/api/dating/draft":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._dating_draft(environ, start_response)
        if path == "/api/banking/parse":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._banking_parse(environ, start_response)
        if path in ("/api/spend/checkin", "/api/lifestyle/itinerary", "/api/settings/commute_lines", "/api/research"):
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._small_post(path, environ, start_response)
        if path == "/api/lifestyle/skin":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._lifestyle_skin(environ, start_response)
        if path == "/api/settings/scout_groups":
            if method not in ("GET", "POST"):
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, POST, OPTIONS")])
                return [b""]
            from apex import scout_common
            if method == "GET":
                return self._respond(start_response, 200, {"groups": scout_common.load_config(self.root).get("meetup_groups")})
            length = environ.get("CONTENT_LENGTH", "")
            if not length.isdecimal() or not 1 <= int(length) <= 4000:
                return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
            try:
                body = json.loads(environ["wsgi.input"].read(int(length)))
                count = scout_common.save_groups(self.root, body.get("groups") if isinstance(body, dict) else None)
            except (json.JSONDecodeError, ValueError):
                return self._respond(start_response, 400, {"error": "GROUP_SHAPE"})
            except OSError:
                return self._respond(start_response, 502, {"error": "CANNOT_WRITE_CONFIG"})
            return self._respond(start_response, 200, {"groups": count})
        if path == "/api/banking/rules":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._banking_rules(environ, start_response)
        if path == "/api/settings/brave_key":
            from apex import brave_search
            if method == "GET":
                return self._respond(start_response, 200, {"set": brave_search.load_key(self.root) is not None, "usage": brave_search.usage(self.root)})
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, POST, OPTIONS")])
                return [b""]
            length = environ.get("CONTENT_LENGTH", "")
            if not length.isdecimal() or not 1 <= int(length) <= 400:
                return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
            try:
                body = json.loads(environ["wsgi.input"].read(int(length)))
                brave_search.save_key(self.root, body.get("key") if isinstance(body, dict) else None)
            except (json.JSONDecodeError, ValueError):
                return self._respond(start_response, 400, {"error": "KEY_SHAPE"})
            except OSError:
                return self._respond(start_response, 502, {"error": "CANNOT_WRITE_KEY"})
            return self._respond(start_response, 200, {"set": True})
        if path == "/api/settings/reed_key":
            if method not in ("GET", "POST"):
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, POST, OPTIONS")])
                return [b""]
            return self._settings_reed(environ, start_response, method)
        if path == "/api/system_health":
            if method != "GET":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, OPTIONS")])
                return [b""]
            from apex import system_health
            return self._respond(start_response, 200, system_health.status(ROOT))
        if path == "/api/system_check":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._system_check(start_response)
        if path == "/api/dating/voice":
            if method not in ("GET", "POST"):
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "GET, POST, OPTIONS")])
                return [b""]
            return self._dating_voice(environ, start_response, method)
        if path == "/api/dating/magnet":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._dating_magnet(environ, start_response)
        if path == "/api/dating/bulk_queue":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._dating_bulk_queue(environ, start_response)
        if path == "/api/wealth/analyze":
            if method != "POST":
                start_response("405 Method Not Allowed", CORS_HEADERS + [("Allow", "POST, OPTIONS")])
                return [b""]
            return self._wealth_analyze(environ, start_response)
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

    def _academic_latest(self, start_response, translate=False):
        # Real, fresh live fetch (same allowlisted RSS hosts A-1 itself uses) for the dashboard's
        # Academic modal - free, no LLM, no budget touched. See
        # orchestrator.academic_latest_titles's own docstring: this is "fetched just now", never
        # a stored history, because no such history exists in the ledger.
        try:
            titles = orchestrator.academic_latest_titles(self.root)
        except Exception:
            return self._respond(start_response, 502, {"error": "ACADEMIC_FETCH_UNAVAILABLE"})
        if translate:
            self._add_persian_titles(titles)
        return self._respond(start_response, 200, {"titles": titles, "fetched_at": time.time()})

    def _add_persian_titles(self, titles):
        """Adds "title_fa" where a translation exists. ONE budget-gated model call covers every
        title not translated before; results are kept in memory only. The titles are untrusted
        feed text: the model's output is used purely as display text, and on any failure the
        English titles are returned unchanged."""
        cache = self.__dict__.setdefault("_title_fa", {})
        missing = [t["title"] for t in titles if isinstance(t.get("title"), str) and t["title"] not in cache][:12]
        if missing:
            key = identifier(f"titles.{int(time.time() * 1000)}"[:48])
            try:
                self.budget.reserve(key, "core", "anthropic", "voice-chat-call", 1)
            except BudgetDenied:
                missing = []
            if missing:
                numbered = "\n".join(f"{i + 1}. {title[:200]}" for i, title in enumerate(missing))
                system = ("Translate each numbered English research-paper title into natural, accurate Persian. "
                          "Keep technical terms and acronyms recognisable. Return ONE JSON object mapping each number "
                          "(as a string) to its Persian title. JSON object only, nothing else.")
                try:
                    raw = call_anthropic(load_api_key(), [{"role": "user", "content": numbered}], system)
                    self.budget.settle(key, 1)
                    start, end = raw.find("{"), raw.rfind("}")
                    parsed = json.loads(raw[start:end + 1]) if 0 <= start < end else {}
                    for index, title in enumerate(missing):
                        value = parsed.get(str(index + 1)) if isinstance(parsed, dict) else None
                        if isinstance(value, str) and 2 <= len(value) <= 300 and re.search(r"[\u0600-\u06FF]", value):
                            if len(cache) > 400:
                                cache.clear()
                            cache[title] = value.strip()
                except Exception:
                    try:
                        self.budget.release(key)
                    except Exception:
                        pass
        for item in titles:
            if item.get("title") in cache:
                item["title_fa"] = cache[item["title"]]

    def _dating_draft(self, environ, start_response):
        # Budget-gated, same SKU/pattern as the voice path (orchestrator.dating_draft_reply) -
        # this is the dashboard modal's direct equivalent, not a second, looser way in. Nothing
        # is stored: the pasted profile text lives only for this one call (see dating_agent.py).
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 6_000_000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        raw = environ["wsgi.input"].read(int(length))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        import dating_agent
        image = body.get("image_b64") if isinstance(body, dict) else None
        profile_text = body.get("profile_text") if isinstance(body, dict) else None
        try:
            if image is not None:
                # A screenshot the owner took themselves; in memory for this one call, never stored.
                drafts = dating_agent.generate_openers_from_image(self.budget, image, body.get("media_type"))
            elif isinstance(profile_text, str) and profile_text.strip() and len(profile_text) <= 4000:
                drafts = (dating_agent.generate_openers(self.budget, profile_text, bold=True) if body.get("bold") is True
                          else dating_agent.generate_openers(self.budget, profile_text))
            else:
                return self._respond(start_response, 400, {"error": "EMPTY_PROFILE_TEXT"})
        except ValueError:
            return self._respond(start_response, 400, {"error": "UNSUPPORTED_IMAGE"})
        except BudgetDenied as exc:
            return self._respond(start_response, 402, {"error": f"BUDGET_DENIED:{exc}"})
        except dating_agent.ResearchPipelineError as exc:
            return self._respond(start_response, 502, {"error": str(exc)})
        return self._respond(start_response, 200, {"drafts": drafts})

    def _banking_parse(self, environ, start_response):
        # The owner's own CSV export, parsed in-memory for this one request only - never
        # stored, no OAuth, no aggregator. Real arithmetic (parsing amounts, summing totals) is
        # pure Python; the one LLM call only classifies descriptions into a fixed category list
        # (see scripts/banking_csv.py's own docstring). Budget-gated like every other LLM call.
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= BANKING_CSV_MAX_BODY_BYTES:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        raw = environ["wsgi.input"].read(int(length))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        csv_text = body.get("csv_text") if isinstance(body, dict) else None
        if not isinstance(csv_text, str):
            return self._respond(start_response, 400, {"error": "MISSING_CSV_TEXT"})
        import banking_csv
        try:
            transactions = banking_csv.parse_transactions(csv_text, details=True)
        except banking_csv.CsvParseError as exc:
            return self._respond(start_response, 400, {"error": f"CSV_PARSE_ERROR:{exc}"})
        # Categories come from fixed keyword rules (apex/deterministic_classifier.py): no model
        # call, no cost, same answer every time. Only totals are kept - per category, and per
        # week for food ordered in or eaten out - so the dashboard can show the owner's weekly
        # limit. No transaction row is stored.
        from apex import deterministic_classifier, scout_common, spending_rules
        summary = deterministic_classifier.summarise(transactions, deterministic_classifier.load_private_rules(self.root))
        now = time.time()
        source = body.get("source_name") if isinstance(body.get("source_name"), str) else "statement"
        try:
            record = spending_rules.merge(scout_common.latest(self.root, "spend"), source, summary, now)
            scout_common.record(self.ledger, "spend", record, now)
            stored = True
        except Exception:
            stored = False
        totals_pence = {c: v["in_pence"] - v["out_pence"] for c, v in summary["totals"].items()}
        return self._respond(start_response, 200, {
            "totals_pence": totals_pence, "transaction_count": summary["transaction_count"],
            "uncategorized_count": summary["uncategorized_count"], "first_date": summary["first_date"],
            "last_date": summary["last_date"], "reconciliation": summary["reconciliation"],
            "signs_flipped": summary["signs_flipped"], "stored_totals": stored})

    def _small_post(self, path, environ, start_response):
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 4000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        if not isinstance(body, dict):
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        from apex import scout_common
        if path == "/api/settings/commute_lines":
            try:
                return self._respond(start_response, 200, {"lines": scout_common.save_groups(self.root, body.get("lines"), "commute_lines")})
            except ValueError:
                return self._respond(start_response, 400, {"error": "LINE_SHAPE"})
            except OSError:
                return self._respond(start_response, 502, {"error": "CANNOT_WRITE_CONFIG"})
        if path == "/api/spend/checkin":
            # The owner's own note about one week's spending, in his words; nothing is inferred from it.
            week, note = body.get("week"), body.get("note")
            if not (isinstance(week, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", week) and isinstance(note, str) and note.strip()):
                return self._respond(start_response, 400, {"error": "WEEK_AND_NOTE_REQUIRED"})
            now = time.time()
            scout_common.record(self.ledger, "checkin", {"event": "spend_checkin", "week_start": week, "note": note.strip()[:600]}, now)
            return self._respond(start_response, 200, {"saved": True})
        from apex import itinerary
        from apex.agents_research import call_anthropic, load_api_key
        try:
            api_key = load_api_key()
        except Exception:
            return self._respond(start_response, 502, {"error": "NO_MODEL"})
        llm = lambda system, user_text, max_tokens: call_anthropic(api_key, system, user_text, max_tokens=max_tokens)  # noqa: E731
        if path == "/api/research":
            import agents_runner
            from apex import research
            from apex import brave_search
            brave_key = brave_search.load_key(self.root)
            institutional = (lambda region, phrase: brave_search.search(self.root, brave_key, region, phrase)) if brave_key else None
            result = research.run(body.get("question") if isinstance(body.get("question"), str) else "",
                                  agents_runner.fetch_public, llm, self.budget, multilingual=body.get("multilingual") is not False,
                                  institutional=institutional)
            if brave_key:
                result["usage"] = brave_search.usage(self.root)
            if result["status"] == "BAD_REQUEST":
                return self._respond(start_response, 400, {"error": "QUESTION_REQUIRED"})
            return self._respond(start_response, 200, result)
        result = itinerary.plan(llm, self.budget, body.get("destination") if isinstance(body.get("destination"), str) else "",
                                body.get("days"), body.get("interests") if isinstance(body.get("interests"), str) else "")
        if result["status"] == "BAD_REQUEST":
            return self._respond(start_response, 400, {"error": "DESTINATION_AND_DAYS_REQUIRED"})
        if result["status"] != "OK":
            denied = str(result.get("model_note", "")).startswith("budget:")
            return self._respond(start_response, 402 if denied else 502, {"error": result.get("model_note") or result["status"]})
        return self._respond(start_response, 200, result)

    def _lifestyle_skin(self, environ, start_response):
        # One selfie -> general cosmetic skincare suggestions, local model only, nothing stored
        # (apex/skin_analyzer.py). Not a skin assessment and not medical advice.
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 6_000_000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        from apex import skin_analyzer
        try:
            text = skin_analyzer.suggest(self.budget, body.get("image_b64") if isinstance(body, dict) else None,
                                         body.get("media_type") if isinstance(body, dict) else None)
        except ValueError:
            return self._respond(start_response, 400, {"error": "UNSUPPORTED_IMAGE"})
        except BudgetDenied as exc:
            return self._respond(start_response, 402, {"error": f"BUDGET_DENIED:{exc}"})
        except skin_analyzer.SkinError as exc:
            return self._respond(start_response, 502, {"error": str(exc)})
        return self._respond(start_response, 200, {"suggestions": text})

    def _banking_rules(self, environ, start_response):
        # The owner's personal keyword rules (local shops, employer, own name on transfers).
        # Stored privately on this server, outside the code repository; never returned.
        from apex import deterministic_classifier
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 40_000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
            rules = deterministic_classifier.check_rules(body.get("rules") if isinstance(body, dict) else None)
            path = self.root.joinpath(*deterministic_classifier.PRIVATE_RULES)
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump({"rules": [[c, list(k)] for c, k in rules]}, out)
        except (json.JSONDecodeError, ValueError):
            return self._respond(start_response, 400, {"error": "RULE_SHAPE"})
        except OSError:
            return self._respond(start_response, 502, {"error": "CANNOT_WRITE_RULES"})
        return self._respond(start_response, 200, {"saved": len(rules)})

    def _settings_reed(self, environ, start_response, method):
        # The owner's own Reed job-search key, typed into his own dashboard. Kept in a private
        # file only the service user can read; never returned, logged or sent anywhere but Reed.
        from apex import scout_wealth
        if method == "GET":
            return self._respond(start_response, 200, {"set": scout_wealth.reed_key() is not None})
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 400:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
            scout_wealth.save_reed_key(self.root, body.get("key") if isinstance(body, dict) else None)
        except (json.JSONDecodeError, ValueError):
            return self._respond(start_response, 400, {"error": "KEY_SHAPE"})
        except OSError:
            return self._respond(start_response, 502, {"error": "CANNOT_WRITE_KEY"})
        return self._respond(start_response, 200, {"set": True})

    def _system_check(self, start_response):
        # Starts scripts/e2e_test.py as its own process (it runs the scouts and one briefing for
        # real, a few minutes on the local model). One at a time; the result is read back through
        # /api/system_health. Nothing in the request is passed to the process.
        import subprocess
        from apex import system_health
        target = ROOT.joinpath(*system_health.E2E_FILE)
        try:
            last = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = {}
        if last.get("state") == "running" and time.time() - float(last.get("started") or 0) < 1800:
            return self._respond(start_response, 429, {"error": "ALREADY_RUNNING"})
        try:
            subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts" / "e2e_test.py"), "--json", str(target)],
                             cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            return self._respond(start_response, 502, {"error": "CANNOT_START"})
        return self._respond(start_response, 200, {"started": True})

    def _dating_voice(self, environ, start_response, method):
        # The owner's own past messages, kept privately on this server as a style sample
        # (apex/ghostwriter.py). GET says only whether a sample exists - it is never sent back.
        from apex import ghostwriter
        if method == "GET":
            return self._respond(start_response, 200, {"saved": bool(ghostwriter.samples(ROOT)),
                                                       "sources": ghostwriter.sources_present(ROOT)})
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 400_000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
            if not isinstance(body, dict):
                raise ValueError("body")
            lines = ghostwriter.save_voice(ROOT, body.get("text"), body.get("source") or "paste")
        except (json.JSONDecodeError, ValueError):
            return self._respond(start_response, 400, {"error": "EMPTY_SAMPLE"})
        except OSError:
            return self._respond(start_response, 502, {"error": "CANNOT_WRITE_SAMPLE"})
        return self._respond(start_response, 200, {"saved": True, "lines": lines})

    def _dating_magnet(self, environ, start_response):
        # The owner's own notes about himself -> bio, post ideas and story replies. Budget-gated
        # (scout-step), nothing stored, nothing posted anywhere (see apex/magnet_profile.py).
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 20_000:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        try:
            body = json.loads(environ["wsgi.input"].read(int(length)))
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        notes = body.get("notes") if isinstance(body, dict) else None
        if not isinstance(notes, str) or not notes.strip():
            return self._respond(start_response, 400, {"error": "EMPTY_NOTES"})
        from apex import magnet_profile
        from apex.agents_research import call_anthropic, load_api_key
        try:
            api_key = load_api_key()
        except Exception:
            return self._respond(start_response, 502, {"error": "NO_MODEL"})
        llm = lambda system, user_text, max_tokens: call_anthropic(api_key, system, user_text, max_tokens=max_tokens)  # noqa: E731
        result = magnet_profile.generate(llm, self.budget, notes)
        if result["status"] != "OK":
            denied = str(result.get("model_note", "")).startswith("budget:")
            return self._respond(start_response, 402 if denied else 502, {"error": result.get("model_note") or result["status"]})
        return self._respond(start_response, 200, result)

    def _dating_bulk_queue(self, environ, start_response):
        # Up to 10 pasted bios, each run through the SAME single-draft path (same SKU, same
        # per-call budget gate) in a plain loop - not a new capability, just this one already-
        # reviewed one applied N times. One bio's budget denial or generation failure never
        # hides the others' real results; nothing here logs into any dating platform.
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 40960:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        raw = environ["wsgi.input"].read(int(length))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        bios = body.get("bios") if isinstance(body, dict) else None
        if not isinstance(bios, list) or not 1 <= len(bios) <= 10 or not all(isinstance(b, str) for b in bios):
            return self._respond(start_response, 400, {"error": "INVALID_BIOS_LIST_MAX_10"})
        import dating_agent
        results = []
        for i, bio in enumerate(bios):
            if not bio.strip():
                results.append({"bio_index": i, "drafts": None, "error": "EMPTY_BIO"})
                continue
            try:
                drafts = dating_agent.generate_openers(self.budget, bio.strip())
                results.append({"bio_index": i, "drafts": drafts, "error": None})
            except BudgetDenied as exc:
                results.append({"bio_index": i, "drafts": None, "error": f"BUDGET_DENIED:{exc}"})
            except dating_agent.ResearchPipelineError as exc:
                results.append({"bio_index": i, "drafts": None, "error": str(exc)})
        return self._respond(start_response, 200, {"results": results})

    def _wealth_analyze(self, environ, start_response):
        # Structural ISA/pension observation only - see core/apex/wealth_engine.py's own
        # docstring for exactly what this is NOT (not a trade, not asset selection, not advice).
        length = environ.get("CONTENT_LENGTH", "")
        if not length.isdecimal() or not 1 <= int(length) <= 4096:
            return self._respond(start_response, 400, {"error": "BAD_CONTENT_LENGTH"})
        raw = environ["wsgi.input"].read(int(length))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._respond(start_response, 400, {"error": "INVALID_JSON"})
        portfolio_text = body.get("portfolio_text") if isinstance(body, dict) else None
        if not isinstance(portfolio_text, str) or not portfolio_text.strip():
            return self._respond(start_response, 400, {"error": "EMPTY_PORTFOLIO_TEXT"})
        from apex.wealth_engine import propose_action, WealthEngineError
        try:
            result = propose_action(self.budget, self.ledger, portfolio_text)
        except WealthEngineError as exc:
            return self._respond(start_response, 400, {"error": str(exc)})
        except BudgetDenied as exc:
            return self._respond(start_response, 402, {"error": f"BUDGET_DENIED:{exc}"})
        except Exception as exc:
            return self._respond(start_response, 502, {"error": f"ANALYSIS_FAILED:{exc}"})
        return self._respond(start_response, 200, result)

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
             "capability-draft-step", "banking-csv-categorize-step", "wealth-analysis-step")
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
    parser.add_argument("--host", default="127.0.0.1",
                         help="Bind address. Keep the default on a server; 0.0.0.0 is for inside a "
                              "container whose port is published to the host's loopback only.")
    parser.add_argument("--reindex-memory", action="store_true",
                         help="Embed every stored conversation turn into semantic memory, then exit.")
    args = parser.parse_args()

    if args.reindex_memory:
        app = VoiceChatApp(ROOT)
        if app.semantic is None:
            sys.exit("Semantic memory is off: set APEX_LLM_PROVIDER=ollama first.")
        rows = app.ledger.db.execute("SELECT seq, session, role, content FROM voice_turns ORDER BY seq").fetchall()
        for seq, session, role, content in rows:
            app.semantic.add("conversation", f"{session}:{seq}", f"({role}) {content}")
        print(f"Indexed {len(rows)} turn(s) with backend {app.semantic.backend}.")
        return

    if args.set_daily_cap_pence is not None:
        set_daily_cap(args.set_daily_cap_pence)
        return

    from waitress import serve
    serve(VoiceChatApp(ROOT), listen=f"{args.host}:{args.port}", threads=4, connection_limit=32)


if __name__ == "__main__":
    main()
