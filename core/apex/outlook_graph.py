"""Microsoft Graph delegated mail: draft creation and header-only listing. There is deliberately no send function.

Verified against learn.microsoft.com (graph-rest-1.0) on 2026-11-12:
- Create message (user-post-messages): POST /me/messages; delegated permission Mail.ReadWrite; JSON body with
  subject, body{contentType,content}, toRecipients[].emailAddress.address; 201 Created; saved in Drafts by default.
- List messages (mailfolder-list-messages): GET /me/mailFolders/{id}/messages; least privileged delegated permission
  Mail.ReadBasic (higher: Mail.ReadWrite, Mail.Read); 200 with `value`; supports OData query parameters.
Also verified 2026-11-12: paging (learn.microsoft.com/graph/paging): when more results exist the response carries `@odata.nextLink`; "Use the entire
URL ... Don't try to extract the $skiptoken or $skip value"; keep following until the property is absent; a page may hold zero or more results and a
requested $top may be ignored or rejected depending on the API. Message resource: `from` is a recipient (recipient.emailAddress), `subject`,
`receivedDateTime` (ISO 8601 UTC) and `id` exist; `$select` is documented for messages. Still NOT confirmed from fetched pages: the emailAddress
sub-property name `address` (taken from the create-message sample), and the maximum $top for this endpoint.
Fixed host graph.microsoft.com. Nothing here has been run live.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlencode, urlsplit

from .agent_contract import wrap_untrusted

HOST = "graph.microsoft.com"
LIMIT = 1_000_000
MAX_SUBJECT = 120
MAX_BODY = 20_000
MAX_RECIPIENTS = 10
TOP = 25
MAX_PAGES = 10
MAX_ITEMS = 200
SELECT_FIELDS = "id,receivedDateTime,from,subject"
REQUIRED_SCOPES = frozenset({"mail.readbasic", "mail.readwrite"})
FORBIDDEN_SCOPES = frozenset({"mail.send", "mail.send.shared", "mail.readwrite.shared"})
BASELINE_SCOPES = frozenset({"openid", "profile", "email", "offline_access", "user.read"})
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,8192}")
FOLDER_ID = re.compile(r"[A-Za-z0-9_=-]{1,512}")
ADDRESS = re.compile(r"[^@\s,;<>()\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
LONG_DIGITS = re.compile(r"\d(?:[ -]?\d){7,}")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
SORT_CODE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


class GraphError(RuntimeError):
    pass


def assert_scopes(granted):
    """Refuse any send-capable scope; require Mail.ReadBasic and Mail.ReadWrite; refuse unknown extra scopes."""
    if isinstance(granted, str):
        granted = granted.split()
    if not isinstance(granted, (list, tuple, set, frozenset)) or not all(isinstance(s, str) for s in granted):
        raise ValueError("granted scopes must be a list of strings")
    have = {s.strip().lower().rsplit("/", 1)[-1] for s in granted if s.strip()}
    if have & FORBIDDEN_SCOPES or any("send" in s for s in have):
        raise GraphError("SEND_SCOPE_REFUSED")
    if not REQUIRED_SCOPES <= have:
        raise GraphError("MISSING_REQUIRED_SCOPES")
    if have - REQUIRED_SCOPES - BASELINE_SCOPES:
        raise GraphError("UNEXPECTED_SCOPES")
    return True


def redact_sensitive(subject):
    """Mask long digit runs, UK sort codes and IBAN-like strings (heuristic, not a guarantee)."""
    out = IBAN.sub("[IBAN]", str(subject))
    out = SORT_CODE.sub("[SORTCODE]", out)
    return LONG_DIGITS.sub("[NUMBER]", out)


def _call(method, path, token, transport, body=None):
    if token is None:
        raise GraphError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid access token")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        status, content_type, raw = transport(method, path, headers, body)
    except Exception:
        raise GraphError("TRANSPORT_ERROR") from None
    if status not in (200, 201):
        raise GraphError(f"GRAPH_HTTP_{status}")            # upstream body is never surfaced or logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip() != "application/json":
        raise GraphError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(raw.decode())
    except ValueError:
        raise GraphError("INVALID_RESPONSE") from None
    if not isinstance(data, dict):
        raise GraphError("INVALID_RESPONSE")
    return status, data


def create_draft(token, to, subject, body, transport):
    """POST /me/messages: creates a draft in Drafts. Never sends. Returns {id, is_draft}."""
    import json
    if not isinstance(to, (list, tuple)) or not 1 <= len(to) <= MAX_RECIPIENTS or not all(isinstance(a, str) and ADDRESS.fullmatch(a) for a in to):
        raise ValueError("to must be 1..10 valid addresses")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or any(ord(c) < 32 for c in subject):
        raise ValueError("Invalid subject")
    if not isinstance(body, str) or not 1 <= len(body) <= MAX_BODY:
        raise ValueError("Invalid body")
    payload = {"subject": subject, "body": {"contentType": "Text", "content": body},
               "toRecipients": [{"emailAddress": {"address": a}} for a in to]}
    status, data = _call("POST", "/v1.0/me/messages", token, transport, json.dumps(payload).encode())
    if status != 201 or data.get("isDraft") is not True or not isinstance(data.get("id"), str):
        raise GraphError("INVALID_RESPONSE")
    return {"id": data["id"], "is_draft": True}


def _next_path(link, folder_id):
    """Validate an @odata.nextLink and return its path+query VERBATIM (never rebuilt) for the transport.

    The credential is forwarded only if the link is https on graph.microsoft.com with no port or userinfo, targets exactly the
    allow-listed folder's messages collection, and carries a query. Microsoft documents that the entire URL must be used as-is and that
    $skiptoken/$skip values are opaque (learn.microsoft.com/graph/paging). The path is compared percent-decoded but forwarded exactly as received.
    """
    if not isinstance(link, str) or not 1 <= len(link) <= 4096 or any(ord(c) < 32 or ord(c) == 127 for c in link):
        raise GraphError("INVALID_NEXT_LINK")
    parsed = urlsplit(link)
    try:
        port = parsed.port
    except ValueError:
        raise GraphError("INVALID_NEXT_LINK") from None
    if (parsed.scheme != "https" or parsed.hostname != HOST or port is not None or parsed.username is not None
            or parsed.password is not None or parsed.fragment or not parsed.query
            or unquote(parsed.path) != f"/v1.0/me/mailFolders/{folder_id}/messages"):
        raise GraphError("INVALID_NEXT_LINK")
    return parsed.path + "?" + parsed.query


def list_headers(token, folder_id, transport, allowlist, top=TOP, max_pages=MAX_PAGES, max_items=MAX_ITEMS):
    """GET /me/mailFolders/{id}/messages for an allow-listed folder; header fields only, subject redacted and truncated.

    Explicit $select (id, receivedDateTime, from, subject) plus $top on the FIRST request only; later pages use the complete
    validated @odata.nextLink. Pages may hold zero or more items and may ignore $top, so only global bounds are enforced.
    Returns {"headers": [...], "pages": n, "truncated": bool}; `truncated` is True when a limit stopped paging before the end.
    """
    if not isinstance(folder_id, str) or not FOLDER_ID.fullmatch(folder_id):
        raise ValueError("Invalid folder_id")
    if type(allowlist) not in (set, frozenset, tuple, list) or folder_id not in allowlist:
        raise GraphError("FOLDER_NOT_ALLOWED")
    if type(top) is not int or not 1 <= top <= 50 or type(max_pages) is not int or not 1 <= max_pages <= 50 \
            or type(max_items) is not int or not 1 <= max_items <= 2000:
        raise ValueError("Invalid paging bounds")
    query = urlencode({"$select": SELECT_FIELDS, "$top": top})
    path = f"/v1.0/me/mailFolders/{folder_id}/messages?{query}"
    out, pages, truncated = [], 0, False
    while path is not None:
        if pages >= max_pages:
            truncated = True
            break
        _, data = _call("GET", path, token, transport)
        pages += 1
        items = data.get("value")
        if not isinstance(items, list) or len(items) > 1000:
            raise GraphError("INVALID_RESPONSE")
        for m in items:
            if len(out) >= max_items:
                truncated = True
                break
            if not isinstance(m, dict) or not isinstance(m.get("id"), str):
                raise GraphError("INVALID_RESPONSE")
            sender = m.get("from")
            address = sender.get("emailAddress", {}).get("address") if isinstance(sender, dict) and isinstance(sender.get("emailAddress"), dict) else None
            subject = redact_sensitive(m.get("subject") or "")[:MAX_SUBJECT]
            out.append({"id": m["id"][:512], "receivedDateTime": str(m.get("receivedDateTime") or "")[:40],
                        "from": str(address or "")[:254], "subject": wrap_untrusted("email", subject)})
        if truncated:
            break
        link = data.get("@odata.nextLink")
        path = None if link is None else _next_path(link, folder_id)
    return {"headers": out, "pages": pages, "truncated": truncated}


def live_transport(method, path, headers, body):           # pragma: no cover - not exercised offline
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, body, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()
