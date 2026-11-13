"""Gmail draft creation ONLY. There is deliberately no send function. Status: TESTS_NOT_RUN.

Verified against developers.google.com on 2026-11-12:
- users.drafts.create: POST https://gmail.googleapis.com/gmail/v1/users/{userId}/drafts (`me` = authenticated user); request body is a
  Draft resource {id, message}; accepted scopes: https://mail.google.com/, .../auth/gmail.modify, .../auth/gmail.compose.
- Message.raw: "The entire email message in an RFC 2822 formatted and base64url encoded string."
Policy (this repository, not a Google statement): only gmail.compose is accepted for drafting. The owner-supplied API hints say compose can also
permit sending, so no-send is enforced in code: this module can only issue POST /gmail/v1/users/me/drafts and refuses every other
method/path, even from a custom transport. Message text is untrusted data; the owner reviews and sends manually in Gmail.
"""
from __future__ import annotations

import base64
import json
import re
from email.message import EmailMessage

HOST = "gmail.googleapis.com"
DRAFTS_PATH = "/gmail/v1/users/me/drafts"
COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
READONLY = "https://www.googleapis.com/auth/gmail.readonly"
REFUSED_SCOPES = frozenset({
    "https://mail.google.com/", "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.insert", "https://www.googleapis.com/auth/gmail.settings.basic"})
LIMIT = 1_000_000
MAX_BODY = 20_000
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,8192}")
ADDRESS = re.compile(r"[^@\s,;<>()\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")


class DraftError(RuntimeError):
    pass


def assert_draft_scopes(granted):
    """Require gmail.compose; refuse broader or send-capable scopes; allow gmail.readonly alongside."""
    if isinstance(granted, str):
        granted = granted.split()
    if not isinstance(granted, (list, tuple, set, frozenset)) or not all(isinstance(s, str) for s in granted):
        raise ValueError("granted scopes must be a list of strings")
    have = {s.strip() for s in granted if s.strip()}
    if have & REFUSED_SCOPES or any("send" in s.lower() for s in have):
        raise DraftError("BROAD_OR_SEND_SCOPE_REFUSED")
    if COMPOSE not in have:
        raise DraftError("MISSING_COMPOSE_SCOPE")
    if have - {COMPOSE, READONLY, "openid", "email", "profile"}:
        raise DraftError("UNEXPECTED_SCOPES")
    return True


def build_raw(to, subject, body):
    """RFC 2822 message as a base64url string, for the Message.raw field."""
    if not isinstance(to, (list, tuple)) or not 1 <= len(to) <= 10 or not all(isinstance(a, str) and ADDRESS.fullmatch(a) for a in to):
        raise ValueError("to must be 1..10 valid addresses")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or any(ord(c) < 32 or ord(c) == 127 for c in subject):
        raise ValueError("Invalid subject")
    if not isinstance(body, str) or not 1 <= len(body) <= MAX_BODY:
        raise ValueError("Invalid body")
    message = EmailMessage()
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def create_draft(token, to, subject, body, transport):
    """POST /gmail/v1/users/me/drafts. `transport(method, path, headers, body)` -> (status, content_type, bytes)."""
    if token is None:
        raise DraftError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid access token")
    payload = json.dumps({"message": {"raw": build_raw(to, subject, body)}}).encode()
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json",
               "Accept-Encoding": "identity"}
    guarded = _GuardedTransport(transport)
    try:
        status, content_type, raw = guarded("POST", DRAFTS_PATH, headers, payload)
    except DraftError:
        raise
    except Exception:
        raise DraftError("TRANSPORT_ERROR") from None
    if status != 200:
        raise DraftError(f"GMAIL_HTTP_{status}")           # upstream body is never surfaced or logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip() != "application/json":
        raise DraftError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(raw.decode())
    except ValueError:
        raise DraftError("INVALID_RESPONSE") from None
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not isinstance(data.get("message"), dict):
        raise DraftError("INVALID_RESPONSE")
    return {"draft_id": data["id"][:256], "sent": False}


class _GuardedTransport:
    """Last line of the no-send rule: only POST to the drafts collection may leave this module."""

    def __init__(self, inner):
        self.inner = inner

    def __call__(self, method, path, headers, body):
        if method != "POST" or path != DRAFTS_PATH:
            raise DraftError("ONLY_DRAFT_CREATION_ALLOWED")
        return self.inner(method, path, headers, body)


def live_transport(method, path, headers, body):            # pragma: no cover - not exercised offline
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, body, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()
