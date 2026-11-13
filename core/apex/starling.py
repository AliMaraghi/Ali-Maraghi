"""Starling Bank Developer API: read-only adapter for the owner's own accounts (accounts, balance, feed).

Details come only from the official starlingbank/starling-developer-sdk (see
docs/apex_status/integrations/starling.md for per-detail provenance): GET /api/v2/accounts,
GET /api/v2/accounts/{accountUid}/balance, GET /api/v2/feed/account/{accountUid}/category/{categoryUid}?changesSince=,
Bearer auth, default host api.starlingbank.com. Every request is an HTTP GET; no write operation exists here.
The transport is injectable; `live_transport` is the only network path. Nothing here has been run
against the live API (TESTS_NOT_RUN, NOT_CONNECTED).
"""
from __future__ import annotations

import os
import re
import stat
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

HOST = "api.starlingbank.com"
LIMIT = 1_000_000              # max response bytes
MAX_ITEMS = 5000               # no paging parameter is confirmed; bound the single response instead
TIMEOUT_SECONDS = 5            # applied by sources.public_http.Connection
OVERLAP_SECONDS = 300          # next_cursor lags the newest updatedAt by this window
MAX_TOKEN_FILE = 4096

# The complete, exact set of operations this module may perform. All are GET.
READ_ONLY_OPERATIONS = frozenset({"accounts", "balance", "feed_changes"})

UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,2048}")
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z")
CURRENCY = re.compile(r"[A-Z]{3}")
_TOKEN_LIKE = re.compile(r"[A-Za-z0-9._~+/=-]{24,}")
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?\S+(?:\s+\S+)?")
_BEARER = re.compile(r"(?i)bearer\s+\S+")

# Values shown by the SDK's recorded feed fixture (test/responses/v2-get-feed-items.json).
STATUS_MAP = {"PENDING": "PDNG", "SETTLED": "BOOK"}
DIRECTIONS = {"OUT": -1, "IN": 1}   # "IN" is not shown in the fixture; see integration doc


class StarlingError(RuntimeError):
    pass


def redact(text):
    """Mask Authorization header values, bearer tokens and any long token-like string."""
    text = str(text)
    text = _AUTH_HEADER.sub(lambda m: m.group(1) + "[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _TOKEN_LIKE.sub("[REDACTED]", text)


def _uuid(name, value):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise ValueError(f"Valid {name} required")
    return value


def _build(op, args):
    if op not in READ_ONLY_OPERATIONS:
        raise ValueError("Unsupported operation")
    if op == "accounts":
        return "/api/v2/accounts"
    account = _uuid("account_uid", args.get("account_uid"))
    if op == "balance":
        return f"/api/v2/accounts/{account}/balance"
    category = _uuid("category_uid", args.get("category_uid"))
    since = args.get("changes_since")
    if not isinstance(since, str) or not RFC3339.fullmatch(since):
        raise ValueError("changes_since must be RFC 3339 UTC")
    return f"/api/v2/feed/account/{account}/category/{category}?" + urlencode({"changesSince": since})


def request(op, token, transport, **args):
    """Return decoded JSON for one read-only call. `transport(method, path, headers)` -> (status, content_type, bytes)."""
    if op not in READ_ONLY_OPERATIONS:
        raise ValueError("Unsupported operation")
    if token is None:
        raise StarlingError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid access token")
    path = _build(op, args)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity"}
    status, content_type, raw = transport("GET", path, headers)
    if status != 200:
        raise StarlingError(f"STARLING_HTTP_{int(status)}")   # path, token and upstream body are never surfaced
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > LIMIT or \
            not isinstance(content_type, str) or content_type.split(";")[0].strip().lower() != "application/json":
        raise StarlingError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(bytes(raw).decode())
    except Exception:
        raise StarlingError("INVALID_RESPONSE") from None
    if not isinstance(data, dict):
        raise StarlingError("INVALID_RESPONSE")
    return data


def live_transport(method, path, headers):                 # pragma: no cover - not exercised offline
    if method != "GET":
        raise ValueError("Only GET is permitted")
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, None, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()


# ---- secure token reference -------------------------------------------------------

def load_token(path):
    """Read a personal access token from a private file. Raises StarlingError('NOT_CONFIGURED') if absent."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise StarlingError("NOT_CONFIGURED") from None
    except OSError:
        raise ValueError("Token file is not accessible") from None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Token file must be a regular file (no symlinks)")
    if info.st_mode & 0o077:
        raise ValueError("Token file must have no group/other permissions")
    if info.st_uid not in (os.getuid(), 0):
        raise ValueError("Token file must be owned by the current user or root")
    if info.st_size > MAX_TOKEN_FILE:
        raise ValueError("Token file too large")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ValueError("Token file is not readable") from None
    try:
        again = os.fstat(fd)
        if (again.st_ino, again.st_dev) != (info.st_ino, info.st_dev):
            raise ValueError("Token file changed while opening")
        raw = os.read(fd, MAX_TOKEN_FILE + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_TOKEN_FILE:
        raise ValueError("Token file too large")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("Token file content invalid") from None
    token = text.strip()
    if "\n" in token or "\r" in token or not TOKEN.fullmatch(token):
        raise ValueError("Token file content invalid")
    return token


# ---- normalisation ----------------------------------------------------------------

def _amount(obj):
    if not isinstance(obj, dict) or type(obj.get("minorUnits")) is not int \
            or not isinstance(obj.get("currency"), str) or not CURRENCY.fullmatch(obj["currency"]):
        raise ValueError("Invalid amount")
    return obj["minorUnits"], obj["currency"]


def list_accounts(token, transport):
    data = request("accounts", token, transport)
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or len(accounts) > 100:
        raise StarlingError("INVALID_RESPONSE")
    out = []
    for a in accounts:
        try:
            if not isinstance(a, dict):
                raise ValueError("Invalid account")
            currency = a.get("currency")
            if not isinstance(currency, str) or not CURRENCY.fullmatch(currency):
                raise ValueError("Invalid account")
            out.append({"account_uid": _uuid("accountUid", a.get("accountUid")),
                        "default_category": _uuid("defaultCategory", a.get("defaultCategory")),
                        "currency": currency})
        except ValueError:
            raise StarlingError("INVALID_RESPONSE") from None
    return out


def get_balance(token, account_uid, transport):
    """Amounts keep the API's integer minorUnits and currency exactly; None when the API omits a field."""
    data = request("balance", token, transport, account_uid=account_uid)
    out = {}
    try:
        for key, name in (("clearedBalance", "cleared"), ("effectiveBalance", "effective"),
                          ("pendingTransactions", "pending")):
            if key in data:
                minor, currency = _amount(data[key])
                out[name] = {"minor": minor, "currency": currency}
            else:
                out[name] = None
    except ValueError:
        raise StarlingError("INVALID_RESPONSE") from None
    if out["cleared"] is None and out["effective"] is None:
        raise StarlingError("INVALID_RESPONSE")
    return out


def normalize_feed_item(item, account_uid, source="starling-api"):
    """Map one feed item to the finance ledger transaction shape. Raises ValueError on anything unexpected."""
    _uuid("account_uid", account_uid)
    if not isinstance(item, dict):
        raise ValueError("Invalid feed item")
    uid = _uuid("feedItemUid", item.get("feedItemUid"))
    minor, currency = _amount(item.get("amount"))
    sign = DIRECTIONS.get(item.get("direction"))
    status = STATUS_MAP.get(item.get("status"))
    when = item.get("transactionTime")
    if sign is None or status is None or not isinstance(when, str) or not RFC3339.fullmatch(when) or minor < 0:
        raise ValueError("Invalid feed item")
    description = item.get("counterPartyName") or item.get("reference") or ""
    if not isinstance(description, str):
        raise ValueError("Invalid feed item")
    return {"date": when[:10], "minor": sign * minor, "currency": currency, "description": description[:256],
            "status": status, "reference": f"{account_uid}/{uid}", "source": source}


def _parse(ts):
    return datetime.strptime(ts.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def fetch_feed_changes(token, account_uid, category_uid, transport, cursor):
    """One incremental read using the SDK's changesSince parameter.

    Returns {"items": [...normalised...], "next_cursor": RFC 3339 UTC}. The cursor is the newest `updatedAt`
    seen minus OVERLAP_SECONDS, never earlier than the caller's cursor; with no items it is unchanged. The
    overlap re-delivers recent items, which is safe because upsert_items() keys by reference. The SDK
    shows no paging parameter, so a response larger than MAX_ITEMS raises PAGE_LIMIT_REACHED.
    """
    data = request("feed_changes", token, transport, account_uid=account_uid, category_uid=category_uid,
                   changes_since=cursor)
    raw_items = data.get("feedItems")
    if not isinstance(raw_items, list):
        raise StarlingError("INVALID_RESPONSE")
    if len(raw_items) > MAX_ITEMS:
        raise StarlingError("PAGE_LIMIT_REACHED")
    items, newest = {}, None
    try:
        for raw in raw_items:
            tx = normalize_feed_item(raw, account_uid)
            updated = raw.get("updatedAt")
            if not isinstance(updated, str) or not RFC3339.fullmatch(updated):
                raise ValueError("Invalid feed item")
            moment = _parse(updated)
            newest = moment if newest is None or moment > newest else newest
            items[tx["reference"]] = tx
    except ValueError:
        raise StarlingError("INVALID_RESPONSE") from None
    next_cursor = cursor
    if newest is not None:
        candidate = (newest - timedelta(seconds=OVERLAP_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if _parse(candidate) > _parse(cursor):
            next_cursor = candidate
    return {"items": list(items.values()), "next_cursor": next_cursor}


def upsert_items(existing, items):
    """Return {"merged": new dict keyed by reference, "changed": sorted keys added/changed}. Inputs are not mutated."""
    merged = {k: dict(v) for k, v in existing.items()}
    changed = []
    for item in items:
        key = item["reference"]
        if merged.get(key) != item:
            changed.append(key)
        merged[key] = dict(item)
    return {"merged": merged, "changed": sorted(set(changed))}
