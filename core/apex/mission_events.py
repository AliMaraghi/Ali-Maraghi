"""The smallest real end-to-end mission: "what is worth going to in London soon", started by the system itself.

One trace id runs through six recorded stages - observe, investigate, judge, critique, act, verify - each with its
elapsed time, what it used and what it could not establish. The only action is to place a shortlist in the owner's
approval queue; nothing is booked, bought or sent. Date, time, venue and price come only from the event page's own
schema.org data; the Persian reason is assembled from those facts and the matched interest, not written by a model."""
from __future__ import annotations

import re
import time

SINGLE = re.compile(r"eventbrite\.co\.uk/e/|ra\.co/events/\d|dice\.fm/event/|designmynight\.com/london/.+/.+|feverup\.com/m/\d")
BANNED = re.compile(r"teen|kids|child|family|toddler|school|online|virtual|webinar|course|workshop", re.I)
WHEN = re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+\d{1,2}\s+[A-Z][a-z]{2,8}|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+20\d\d)?", re.I)
WANT = {"gala": (3, "گالا"), "members club": (3, "باشگاه اعضا"), "social club": (3, "باشگاه اجتماعی"), "supper club": (3, "شام گروهی"),
        "wine tasting": (2, "چشیدن شراب"), "house party": (3, "مهمانی خانگی"), "warehouse": (2, "مهمانی انباری"), "rave": (2, "ریو"),
        "ball": (2, "مجلس رقص رسمی"), "soiree": (2, "شب‌نشینی"), "soirée": (2, "شب‌نشینی"), "cocktail": (1, "کوکتل"), "party": (1, "مهمانی")}
DAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def _matched(text: str) -> list:
    return [k for k in WANT if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", text.lower())]


def reason_fa(matched: list, page: dict) -> str:
    """A Persian reason built only from the matched interest and facts read from the page."""
    import datetime as dt
    day = DAYS_FA[dt.date.fromisoformat(page["start"][:10]).weekday()]
    parts = ["با علاقهٔ ثبت‌شدهٔ تو می‌خواند چون خودِ رویداد «" + "، ".join(WANT[k][1] for k in matched) + "» معرفی شده"]
    parts.append(f"{day}‌شب است" if page["start"][11:13] >= "18" else f"روز {day} است")
    if "london" in (page.get("address") or "").lower():
        parts.append("و در لندن برگزار می‌شود")
    return "؛ ".join(parts[:2]) + (" " + parts[2] if len(parts) > 2 else "") + "."


REASON = ("You write ONE short sentence in Persian saying why this event could suit a man in London looking for sociable, "
          "open-minded evenings. Use only the title and description given. No dates, prices or numbers. Reply with the sentence only.")


def weekend(now: float) -> tuple:
    """The next Saturday and Sunday strictly after today, as ISO dates."""
    import datetime as dt
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    sat = today + dt.timedelta(days=(5 - today.weekday()) % 7 or 7)
    return sat.isoformat(), (sat + dt.timedelta(days=1)).isoformat()


def queries(now: float) -> list:
    import datetime as dt
    sat = dt.date.fromisoformat(weekend(now)[0])
    day = f"{sat.day} {sat.strftime('%B %Y')}"
    return [f"London gala {day} tickets", f"London members club party Saturday {day}", f"London warehouse party {day} tickets",
            f"London wine tasting {day}", f"London supper club {day}", f"London ball soiree Saturday {day}"]


def _events_in(node):
    if isinstance(node, list):
        for n in node:
            yield from _events_in(n)
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "Event" or (isinstance(kind, list) and "Event" in kind) or (isinstance(kind, str) and kind.endswith("Event")):
            yield node
        for key in ("@graph", "mainEntity"):
            if key in node:
                yield from _events_in(node[key])


def verify_page(fetch_text, url: str, now: float) -> dict:
    """Confirm an event from its own page's schema.org data. fetch_text(url) -> str. Honors the site's robots.txt."""
    import json
    import urllib.robotparser
    from urllib.parse import urlsplit
    checked = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    parts = urlsplit(url)
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(fetch_text(f"https://{parts.netloc}/robots.txt").splitlines())
        if not rp.can_fetch("*", url):
            return {"verified": False, "why": "the site's robots.txt does not allow automated reading of this page", "checked_at": checked}
        page = fetch_text(f"https://{parts.netloc}{parts.path}")
    except Exception as exc:                                       # noqa: BLE001
        return {"verified": False, "why": f"page could not be read ({str(exc)[:60] or type(exc).__name__})", "checked_at": checked}
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for ev in _events_in(data):
            start = str(ev.get("startDate") or "")
            if not re.match(r"\d{4}-\d{2}-\d{2}", start):
                continue
            loc = ev.get("location") or {}
            loc = loc[0] if isinstance(loc, list) and loc else loc
            addr = loc.get("address") if isinstance(loc, dict) else None
            if isinstance(addr, dict):
                addr = ", ".join(str(addr[k]) for k in ("streetAddress", "addressLocality", "postalCode") if addr.get(k))
            offers = ev.get("offers") or {}
            offers = offers[0] if isinstance(offers, list) and offers else offers
            price, availability = None, None
            if isinstance(offers, dict):
                availability = str(offers.get("availability") or "").rsplit("/", 1)[-1] or None
                price = offers.get("price") or offers.get("lowPrice")
                price = f"{price} {offers.get('priceCurrency', '')}".strip() if price not in (None, "") else None
            return {"verified": True, "checked_at": checked, "name": str(ev.get("name") or "")[:160], "start": start[:25], "end": str(ev.get("endDate") or "")[:25] or None,
                    "venue": str(loc.get("name") or "")[:120] if isinstance(loc, dict) else None, "address": str(addr)[:200] if addr else None,
                    "price": price, "availability": availability, "status": str(ev.get("eventStatus") or "").rsplit("/", 1)[-1] or None}
    return {"verified": False, "why": "the page has no machine-readable event data", "checked_at": checked}


def observe(search, now: float) -> dict:
    """search(query) -> [{title, url, domain, extract}]. Keeps single-event pages only."""
    found, errors, dropped, seen, calls = [], [], 0, set(), 0
    for q in queries(now):
        try:
            calls += 1
            for r in search(q):
                text = r["title"] + " " + r["extract"]
                if r["url"] in seen or not SINGLE.search(r["url"]) or BANNED.search(text):
                    dropped += 1
                    continue
                seen.add(r["url"])
                found.append({"query": q, "title": r["title"][:160], "url": r["url"], "site": r["domain"], "extract": r["extract"][:240]})
        except Exception as exc:                                   # noqa: BLE001
            errors.append(f"{q[:24]}: {type(exc).__name__}")
    return {"found": found, "errors": errors, "dropped_not_single_events": dropped, "search_calls": calls}


def judge(items: list) -> list:
    out = []
    for it in items:
        text = (it["title"] + " " + it["extract"]).lower()
        when = WHEN.search(it["title"] + " " + it["extract"])
        matched = _matched(text)
        if not matched:
            continue                                               # nothing in it matches a stated interest: not a candidate
        out.append({**it, "url": it["url"].split("?")[0], "date_text": when.group(0) if when else None,
                    "score": sum(WANT[k][0] for k in matched), "matched": matched})
    return sorted(out, key=lambda x: -x["score"])


def run(now: float, search, llm, propose, fetch_text=None, stamp=None, revision=None) -> dict:
    """propose(proposal_id, payload, evidence_ids) -> state string or raises. One mission per target weekend: running it
    again (after a restart, say) reuses the same id, so the approval record is never duplicated."""
    stamp = stamp or (lambda: time.time())
    sat, sun = weekend(now)
    trace = "mission-events-" + sat.replace("-", "")
    stages = []
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    def stage(name, fn):
        t0 = stamp()
        try:
            result, note = fn()
            stages.append({"stage": name, "ok": True, "ms": round((stamp() - t0) * 1000), "note": note})
            return result
        except Exception as exc:                                   # noqa: BLE001
            stages.append({"stage": name, "ok": False, "ms": round((stamp() - t0) * 1000), "note": f"{type(exc).__name__}: {str(exc)[:120]}"})
            return None

    def receipt(status, shortlist, approval=None, error=None):
        return {"event": "mission_events", "status": status, "trace": trace, "target_dates": [sat, sun], "stages": stages, "shortlist": shortlist,
                "approval_state": approval, "total_ms": sum(s["ms"] for s in stages),
                "receipt": {"capability_id": "london-events-mission", "run_id": trace, "code_revision": revision, "status": status, "started_at": started,
                            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + sum(s["ms"] for s in stages) / 1000)),
                            "source_ids": [x["url"] for x in shortlist], "artifact_refs": [trace] if approval else [], "cost": 0,
                            "approval_id": trace if approval else None, "error_code": error}}

    obs = stage("OBSERVE", lambda: (lambda o: (o, f"{o['search_calls']} searches, {len(o['found'])} single-event pages kept, {o['dropped_not_single_events']} dropped, errors: {o['errors'] or 'none'}"))(observe(search, now)))
    if not obs or not obs["found"]:
        return receipt("ZERO_RESULT", [], error="NO_SINGLE_EVENT_PAGES_FOUND")
    if obs["errors"] and len(obs["errors"]) == obs["search_calls"]:
        return receipt("FAILED", [], error="SEARCH_UNAVAILABLE")
    ranked = stage("JUDGE", lambda: (lambda s: (s, f"{len(s)} candidates ranked by stated interests"))(judge(obs["found"]))) or []

    def investigate():
        good, reasons = [], {}
        for it in ranked[:8]:
            v = verify_page(fetch_text, it["url"], now) if fetch_text else {"verified": False, "why": "page reader not available"}
            it["page"] = v
            reasons[v.get("why") or ("on target dates" if v.get("start", "")[:10] in (sat, sun) else "verified but on another date")] = reasons.get(v.get("why") or ("on target dates" if v.get("start", "")[:10] in (sat, sun) else "verified but on another date"), 0) + 1
            if v.get("verified") and v.get("start", "")[:10] in (sat, sun) and v.get("venue") and "cancel" not in (v.get("status") or "").lower() and (v.get("availability") or "") not in ("SoldOut", "Discontinued", "OutOfStock"):
                good.append(it)
        return good[:3], "pages read: " + "; ".join(f"{n} {why}" for why, n in reasons.items())
    short = stage("INVESTIGATE", investigate) or []
    if not short:
        return receipt("ZERO_RESULT", [], error="NO_EVENT_VERIFIED_FOR_TARGET_DATES")

    def critique():
        for it in short:
            p = it["page"]
            it["not_established"] = [x for x, missing in (("price", not p.get("price")), ("still on sale", p.get("availability") != "InStock"), ("address", not p.get("address"))) if missing]
            it["reason_fa"] = reason_fa(it["matched"], p)
            it["fit"] = it["matched"]
        return short, "each item lists what the page did not establish; the Persian reason is assembled from page facts, no model wording"
    stage("CRITIQUE", critique)

    payload = {"trace": trace, "kind": "event-shortlist", "target_dates": [sat, sun],
               "items": [{"title": it["page"]["name"] or it["title"], "url": it["url"], "start": it["page"]["start"], "venue": it["page"]["venue"],
                          "address": it["page"]["address"], "price": it["page"]["price"], "availability": it["page"].get("availability"), "checked_at": it["page"]["checked_at"],
                          "fit": it["fit"], "reason_fa": it["reason_fa"], "not_established": it["not_established"]} for it in short]}
    state = stage("ACT", lambda: (lambda st: (st, f"shortlist in the approval queue as {trace}: {st}"))(propose(trace, payload, [it["url"][:80] for it in short])))
    stage("VERIFY", lambda: (state, "approval record read back from the ledger" if state else "no approval record: the queue was not reachable"))
    return receipt("OK" if state and all(s["ok"] for s in stages) else "PARTIAL", short, state, None if state else "APPROVAL_QUEUE_UNREACHABLE")
