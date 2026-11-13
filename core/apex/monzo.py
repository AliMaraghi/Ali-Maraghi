"""Monzo Developer API: read-only adapter for the owner's own account (accounts, balance, transactions).

Endpoints, parameters and response fields verified against https://docs.monzo.com/ on 2026-11-12:
GET /accounts (optional account_type), GET /balance?account_id=, GET /transactions?account_id=&since=&before=&limit=
(limit default 30, max 100; full history only in the first 5 minutes after authentication, then 90 days).
No write operations exist here. The transport is injectable; `live_transport` is the only network path and is
pinned to api.monzo.com. Nothing here has been run against the live API.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlencode

HOST = "api.monzo.com"
PAGE = 100
MAX_PAGES = 50
FULL_HISTORY_SECONDS = 300
LIMIT = 1_000_000

ACCOUNT_ID = re.compile(r"acc_[A-Za-z0-9]{10,64}")
TOKEN = re.compile(r"[A-Za-z0-9._-]{20,8192}")
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z")
OBJECT_ID = re.compile(r"tx_[A-Za-z0-9]{10,64}")


class MonzoError(RuntimeError):
    pass


def _build(op, args):
    if op == "accounts":
        return "/accounts"
    account = args.get("account_id")
    if not isinstance(account, str) or not ACCOUNT_ID.fullmatch(account):
        raise ValueError("Valid account_id required")
    if op == "balance":
        return "/balance?" + urlencode({"account_id": account})
    if op != "transactions":
        raise ValueError("Unsupported operation")
    query = {"account_id": account}
    limit = args.get("limit", PAGE)
    if type(limit) is not int or not 1 <= limit <= PAGE:
        raise ValueError("limit must be 1..100")
    query["limit"] = limit
    for name in ("since", "before"):
        value = args.get(name)
        if value is not None:
            if not isinstance(value, str) or not (RFC3339.fullmatch(value) or (name == "since" and OBJECT_ID.fullmatch(value))):
                raise ValueError(f"{name} must be RFC 3339 UTC" + (" or a transaction id" if name == "since" else ""))
            query[name] = value
    return "/transactions?" + urlencode(query)


def request(op, token, transport, **args):
    """Return decoded JSON for one read-only call. `transport(method, path, headers)` -> (status, content_type, bytes)."""
    if token is None:
        raise MonzoError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid access token")
    path = _build(op, args)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity"}
    status, content_type, raw = transport("GET", path, headers)
    if status != 200:
        raise MonzoError(f"MONZO_HTTP_{status}")           # upstream body is never surfaced or logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip() != "application/json":
        raise MonzoError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    data = strict_json(raw.decode())
    if not isinstance(data, dict):
        raise MonzoError("INVALID_RESPONSE")
    return data


def live_transport(method, path, headers):                 # pragma: no cover - not exercised offline
    from .sources.public_http import Connection, resolve_public
    family, address = resolve_public(HOST)
    conn = Connection(HOST, family, address)
    try:
        conn.request(method, path, None, {**headers, "Connection": "close"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read(LIMIT + 1)
    finally:
        conn.close()


# ---- normalisation into the finance ledger's shapes ------------------------------

def normalize_balance(data):
    if type(data.get("balance")) is not int or not isinstance(data.get("currency"), str) or len(data["currency"]) != 3:
        raise ValueError("Invalid balance response")
    return {"type": "CURRENT", "minor": data["balance"], "currency": data["currency"],
            "spend_today_minor": data.get("spend_today") if type(data.get("spend_today")) is int else None}


def normalize_transaction(t, source="monzo-api"):
    if type(t.get("amount")) is not int or not isinstance(t.get("id"), str) or not isinstance(t.get("created"), str):
        raise ValueError("Invalid transaction")
    merchant = t.get("merchant")
    name = merchant.get("name") if isinstance(merchant, dict) else None
    declined = bool(t.get("decline_reason"))
    return {"date": t["created"][:10], "minor": t["amount"], "currency": str(t.get("currency", ""))[:3],
            "description": str(name or t.get("description") or "")[:256],
            "status": "DECL" if declined else ("BOOK" if t.get("settled") else "PDNG"),
            "reference": t["id"][:128], "source": source}


def coverage(authenticated_at, now):
    """Honest history coverage under Monzo's 5-minute rule (datetimes or epoch seconds)."""
    to_epoch = lambda v: v.timestamp() if isinstance(v, datetime) else float(v)
    return "FULL_HISTORY" if to_epoch(now) - to_epoch(authenticated_at) <= FULL_HISTORY_SECONDS else "LAST_90_DAYS"


def fetch_transactions(token, account_id, transport, since=None, include_declined=False):
    """Paginate forward by transaction id; de-duplicate; bounded by MAX_PAGES."""
    seen, out, cursor = set(), [], since
    for _ in range(MAX_PAGES):
        args = {"account_id": account_id, "limit": PAGE}
        if cursor:
            args["since"] = cursor
        page = request("transactions", token, transport, **args).get("transactions")
        if not isinstance(page, list):
            raise MonzoError("INVALID_RESPONSE")
        for raw in page:
            tx = normalize_transaction(raw)
            if tx["reference"] in seen:
                continue
            seen.add(tx["reference"])
            if tx["status"] != "DECL" or include_declined:
                out.append(tx)
        if len(page) < PAGE:
            return out
        cursor = page[-1]["id"]
    raise MonzoError("PAGE_LIMIT_REACHED")
