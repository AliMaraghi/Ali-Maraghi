"""YouTube Data API v3: read-only channel statistics for daily snapshots (own channel). Status: TESTS_NOT_RUN, NOT_CONNECTED.

Verified against developers.google.com/youtube/v3 on 2026-11-12: `GET https://www.googleapis.com/youtube/v3/channels`; `part` required (`statistics` is a valid value);
exactly one filter (`mine=true` returns the authenticated user's channels and needs an authorized request; more than one filter -> 400 invalidCriteria);
`maxResults` 0-50 (default 5); response `{kind: "youtube#channelListResponse", items:[channel], pageInfo:{totalResults, resultsPerPage}, nextPageToken?}`;
cost 1 quota unit per call. Channel resource: `id` (string), `statistics.viewCount|subscriberCount|videoCount` (unsigned long in the reference),
`statistics.hiddenSubscriberCount` (boolean); `subscriberCount` "is rounded down to three significant figures".
Scope: `youtube.readonly` ("read-only access to your YouTube account", Google OAuth scope table, 2026-11-12) is the accepted requirement for `channels.list` with `mine=true`.
Provenance: owner statement of 2026-11-12 (the owner's message wrote the scope as "https://googleapis.com", which is not a valid scope URL and is read as
https://www.googleapis.com/auth/youtube.readonly). The channels.list page itself says only "properly authorized"; this is not a provider-documentation confirmation. All other YouTube scopes are refused.
Still NOT confirmed: the JSON encoding of the counts (reference says unsigned long; both integers and decimal strings are accepted here) and the daily quota limit. GET only; no upload/publish/comment function exists.
"""
from __future__ import annotations

import re

from .social_snapshots import validate_row

HOST = "www.googleapis.com"
PATH = "/youtube/v3/channels?part=statistics&mine=true&maxResults=50"
READONLY = "https://www.googleapis.com/auth/youtube.readonly"
REFUSED = frozenset({
    "https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtubepartner",
    "https://www.googleapis.com/auth/youtubepartner-channel-audit"})
LIMIT = 1_000_000
MAX_CHANNELS = 50
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,8192}")
CHANNEL_ID = re.compile(r"[A-Za-z0-9_-]{10,64}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class YouTubeError(RuntimeError):
    pass


def assert_scopes(granted):
    if isinstance(granted, str):
        granted = granted.split()
    if not isinstance(granted, (list, tuple, set, frozenset)) or not all(isinstance(s, str) for s in granted):
        raise ValueError("granted scopes must be a list of strings")
    have = {s.strip() for s in granted if s.strip()}
    if have & REFUSED or any(s.startswith("https://www.googleapis.com/auth/youtube") and s != READONLY for s in have):
        raise YouTubeError("WRITE_CAPABLE_SCOPE_REFUSED")
    if READONLY not in have:
        raise YouTubeError("MISSING_READONLY_SCOPE")
    return True


def _count(value):
    if type(value) is int and 0 <= value <= 10**12:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{1,13}", value):
        return int(value)
    raise ValueError("Invalid count")


def fetch_channel_snapshots(token, date, transport):
    """One GET; returns a list of validated snapshot rows (platform 'youtube', source 'api'), one per channel.

    `transport(method, path, headers)` -> (status, content_type, bytes). Subscriber counts are omitted when the channel hides them
    and are rounded by YouTube (note recorded on each row). Only the first page (<= 50 channels) is read; more raises PAGE_LIMIT_REACHED.
    """
    if token is None:
        raise YouTubeError("NOT_CONFIGURED")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid access token")
    if not isinstance(date, str) or not DATE.fullmatch(date):
        raise ValueError("date must be YYYY-MM-DD")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity"}
    try:
        status, content_type, raw = transport("GET", PATH, headers)
    except Exception:
        raise YouTubeError("TRANSPORT_ERROR") from None
    if status != 200:
        raise YouTubeError(f"YOUTUBE_HTTP_{int(status)}")      # upstream body is never surfaced or logged
    if len(raw) > LIMIT or content_type.split(";")[0].strip().lower() != "application/json":
        raise YouTubeError("INVALID_RESPONSE")
    from .kernel.schema import strict_json
    try:
        data = strict_json(raw.decode())
    except ValueError:
        raise YouTubeError("INVALID_RESPONSE") from None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > MAX_CHANNELS:
        raise YouTubeError("INVALID_RESPONSE")
    if data.get("nextPageToken"):
        raise YouTubeError("PAGE_LIMIT_REACHED")
    rows = []
    try:
        for channel in items:
            stats = channel.get("statistics")
            channel_id = channel.get("id")
            if not isinstance(stats, dict) or not isinstance(channel_id, str) or not CHANNEL_ID.fullmatch(channel_id):
                raise ValueError("Invalid channel")
            metrics = {"views": _count(stats.get("viewCount")), "posts": _count(stats.get("videoCount"))}
            if stats.get("hiddenSubscriberCount") is not True and "subscriberCount" in stats:
                metrics["followers"] = _count(stats["subscriberCount"])
            row = validate_row({"platform": "youtube", "date": date, "source": "api", "account_label": channel_id,
                                "metrics": metrics})
            row["notes"] = ["subscriberCount is rounded down to three significant figures by YouTube"]
            rows.append(row)
    except ValueError:
        raise YouTubeError("INVALID_RESPONSE") from None
    return rows


def live_transport(method, path, headers):                      # pragma: no cover - not exercised offline
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
