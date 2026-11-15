"""Read-only telemetry event bus + Server-Sent Events stream (mission 2026-11-15).

Captures kernel state changes (domain-router activity, proposal generation, HITL alerts) as
an append-only, in-memory event log and streams them to any connected listener as SSE
(`text/event-stream`), so the owner sees what the backend is doing without polling or
refreshing the page.

STRICTLY READ-ONLY BY CONSTRUCTION: this module has exactly one mutating method
(`EventBus.publish`), and it only appends an event to an in-memory ring buffer - it cannot
execute, approve, or change anything in the Ledger, Budget, or ApprovalBook. Nothing in this
file calls `ApprovalBook.approve`/`execute`/`issue`, and it deliberately does NOT expose a
"submit an approval" endpoint - see docs/apex_status/TELEMETRY_BRIDGE_NOTES.md for why: a
bare `POST /api/v1/approvals/{id}` without the existing signed-nonce/expiry/identity checks
`ApprovalBook` already enforces would be a weaker, parallel approval path, which is a
security regression, not a feature. The real approval action stays exactly where it already
is - the existing, Access-gated console - this module only tells the owner that one is
waiting.

No FastAPI/uvicorn here, matching scripts/voice_api.py's own documented reason (uvicorn is
not installed on this Debian-managed Python, and `pip install` without --break-system-packages
refuses it): this is a plain WSGI generator, servable by `waitress` like every other service
in this codebase.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque

HITL_REQUIRED = "HITL_REQUIRED"
KERNEL_EVENT = "KERNEL"
STREAM_PATH = "/api/v1/telemetry/stream"


class EventBus:
    """An in-memory, append-only ring buffer of events, with one mutating method
    (publish) and two read-only ones (since, latest_seq). Thread-safe (a single lock) -
    this is a low-volume, human-observable event stream, not a high-throughput queue."""

    def __init__(self, maxlen: int = 500):
        self._events: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def publish(self, event_type: str, detail: dict) -> dict:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "ts": time.time(), "type": event_type, "detail": detail}
            self._events.append(event)
        return event

    def since(self, seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq


# Module-level default bus - the one every real caller (agents_runner.py) publishes to and
# the one the real SSE server streams from. Tests construct their own EventBus() instead of
# touching this one, so test runs never pollute or depend on process-global state.
DEFAULT_BUS = EventBus()


def sse_format(event: dict) -> str:
    """Standard SSE wire format: id/event/data lines, blank line terminator."""
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


def stream_events(bus: EventBus, start_seq: int = 0, poll_interval: float = 0.2, max_polls: int | None = None):
    """Generator yielding SSE-formatted text for every event published after start_seq.
    `max_polls` bounds the loop for tests (no real sleep needed - a test publishes between
    calls to next() on this generator); the real WSGI app passes max_polls=None and runs
    until the client disconnects."""
    seq = start_seq
    polls = 0
    while max_polls is None or polls < max_polls:
        for event in bus.since(seq):
            seq = event["seq"]
            yield sse_format(event)
        polls += 1
        if max_polls is None:
            time.sleep(poll_interval)


def sse_wsgi_app(bus: EventBus, allowed_origin: str = "https://ui.apexcorelab.uk"):
    """A plain WSGI callable serving STREAM_PATH as text/event-stream. GET/HEAD only -
    there is no write method on this path, by design (see module docstring)."""

    def app(environ, start_response):
        if environ.get("PATH_INFO") != STREAM_PATH:
            start_response("404 Not Found", [("Content-Type", "application/json")])
            return [json.dumps({"error": "NOT_FOUND"}).encode("utf-8")]
        method = environ.get("REQUEST_METHOD")
        if method not in ("GET", "HEAD"):
            start_response("405 Method Not Allowed", [("Allow", "GET, HEAD")])
            return [b""]
        headers = [("Content-Type", "text/event-stream; charset=utf-8"),
                   ("Cache-Control", "no-cache"),
                   ("Access-Control-Allow-Origin", allowed_origin),
                   ("X-Accel-Buffering", "no")]
        start_response("200 OK", headers)
        if method == "HEAD":
            return [b""]
        try:
            last_seq = int(environ.get("HTTP_LAST_EVENT_ID") or 0)
        except ValueError:
            last_seq = 0
        return (chunk.encode("utf-8") for chunk in stream_events(bus, last_seq))

    return app
