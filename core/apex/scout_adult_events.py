"""Adults-only / open-minded London events: reads what organisers publish openly, nothing else.

Source: the schema.org event list (JSON-LD) that Humanitix puts on every public host page,
https://events.humanitix.com/host/<host> - no login, no API key. The default host is Feeld's
own page, whose London socials are listed there.

Not used, deliberately: FetLife and FabSwingers show events only to signed-in members, so
reading them would mean automating a personal account against their terms; Killing Kittens
publishes no feed or structured data. Those appear on the dashboard as plain links the owner
opens himself.

It only reads and lists. No model call, no cost, no RSVP, no account.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone

from . import scout_common as common

HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,79}")
LD = re.compile(rb'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
EVENT_URL = re.compile(r"https://events\.humanitix\.com/[A-Za-z0-9][A-Za-z0-9_-]{0,150}")
HORIZON_DAYS, TOP = 90, 5
DEFAULT_HOSTS = ["feeldco"]
# What the owner asked to be flagged first. Matching is on the published title only.
PRIORITY = ("under 35", "under-35", "u35", "munch", "kink", "bdsm", "group play", "rave", "lifestyle")
KEYWORDS = PRIORITY + ("social", "cabaret", "party", "play", "singles")


def host_url(host: str) -> str:
    if not isinstance(host, str) or not HOST.fullmatch(host):
        raise ValueError("Invalid host name")
    return f"https://events.humanitix.com/host/{host}"


def parse(raw: bytes, host: str) -> list:
    events = []
    for block in LD.findall(raw[:common.MAX_FEED_BYTES]):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "ItemList":
            continue
        for entry in data.get("itemListElement") or []:
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict) or item.get("@type") != "Event":
                continue
            url, start = item.get("url"), item.get("startDate")
            if not (isinstance(url, str) and EVENT_URL.fullmatch(url) and isinstance(start, str)):
                continue
            try:
                when = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            place = item.get("location") if isinstance(item.get("location"), dict) else {}
            address = place.get("address") if isinstance(place.get("address"), dict) else {}
            street = common.clean(address.get("streetAddress"), 120)
            events.append({"title": common.clean(item.get("name"), 120), "start": when.strftime("%Y-%m-%d %H:%M"),
                           "location": common.clean(place.get("name"), 80), "address": street,
                           "in_london": "london" in (street + " " + str(address.get("addressLocality") or "")).lower(),
                           "url": url, "host": host})
    return [e for e in events if e["title"]]


def run(config: dict, fetch, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    hosts = config.get("adult_event_hosts")
    hosts = hosts if isinstance(hosts, list) else DEFAULT_HOSTS
    found, failed = [], []
    for host in hosts[:10]:
        try:
            found += parse(fetch(host_url(host)), host)
        except Exception as exc:                       # a renamed or unreachable host is not a crash
            failed.append(f"{host}:{type(exc).__name__}")
    seen, upcoming = set(), []
    for event in sorted(found, key=lambda e: e["start"]):
        when = datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
        if event["in_london"] and today <= when <= today + timedelta(days=HORIZON_DAYS) and event["url"] not in seen:
            seen.add(event["url"])
            event["matched"] = [k for k in KEYWORDS if k in event["title"].lower()]
            upcoming.append(event)
    upcoming.sort(key=lambda e: (not any(k in e["matched"] for k in PRIORITY), e["start"]))
    return {"event": "scout_adult_events", "status": "OK" if upcoming else "NO_EVENTS", "hosts": len(hosts),
            "feeds_failed": failed, "considered": len(found), "picked": upcoming[:TOP]}
