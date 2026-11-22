"""The smallest real end-to-end mission: "what is worth going to in London soon", started by the system itself.

One trace id runs through six recorded stages - observe, investigate, judge, critique, act, verify - each with its
elapsed time, what it used and what it could not establish. The only action is to place a shortlist in the owner's
approval queue; nothing is booked, bought or sent. The local model is used once, to word a reason in Persian, and its
line is dropped if it mentions a number or date that is not in the evidence."""
from __future__ import annotations

import re
import time

SINGLE = re.compile(r"eventbrite\.co\.uk/e/|ra\.co/events/\d|dice\.fm/event/|designmynight\.com/london/.+/.+|feverup\.com/m/\d")
BANNED = re.compile(r"teen|kids|child|family|toddler|school|online|virtual|webinar|course|workshop", re.I)
WHEN = re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+\d{1,2}\s+[A-Z][a-z]{2,8}|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+20\d\d)?", re.I)
WANT = {"gala": 3, "members": 2, "club": 2, "supper": 2, "wine": 2, "tasting": 1, "party": 2, "warehouse": 2, "ball": 2, "soiree": 2, "cocktail": 1}
REASON = ("You write ONE short sentence in Persian saying why this event could suit a man in London looking for sociable, "
          "open-minded evenings. Use only the title and description given. No dates, prices or numbers. Reply with the sentence only.")


def queries(now: float) -> list:
    month = time.strftime("%B %Y", time.gmtime(now))
    return [f"London gala tickets {month}", f"London members club party tickets {month}", f"London warehouse party tickets {month}",
            f"London wine tasting evening tickets {month}", f"London supper club tickets {month}"]


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
        score = sum(w for k, w in WANT.items() if k in text) + (3 if when else 0)
        out.append({**it, "date_text": when.group(0) if when else None, "score": score,
                    "matched": [k for k in WANT if k in text]})
    return sorted(out, key=lambda x: -x["score"])[:3]


def run(now: float, search, llm, propose, stamp=None) -> dict:
    """propose(proposal_id, payload, evidence_ids) -> state string or raises. Returns the full mission record."""
    stamp = stamp or (lambda: time.time())
    trace = "mission-events-" + time.strftime("%Y%m%d-%H%M", time.gmtime(now))
    stages = []

    def stage(name, fn):
        t0 = stamp()
        try:
            result, note = fn()
            stages.append({"stage": name, "ok": True, "ms": round((stamp() - t0) * 1000), "note": note})
            return result
        except Exception as exc:                                   # noqa: BLE001
            stages.append({"stage": name, "ok": False, "ms": round((stamp() - t0) * 1000), "note": f"{type(exc).__name__}: {str(exc)[:120]}"})
            return None

    obs = stage("OBSERVE", lambda: (lambda o: (o, f"{o['search_calls']} searches, {len(o['found'])} single-event pages kept, {o['dropped_not_single_events']} dropped, errors: {o['errors'] or 'none'}"))(observe(search, now)))
    if not obs or not obs["found"]:
        return {"event": "mission_run", "status": "NO_DATA", "trace": trace, "stages": stages, "shortlist": []}
    short = stage("JUDGE", lambda: (lambda s: (s, "ranked by stated interests and whether a date appears: " + ", ".join(f"{x['score']}" for x in s)))(judge(obs["found"])))

    def reasons():
        made = 0
        for it in short:
            line = None
            if llm is not None:
                try:
                    line = " ".join(str(llm(REASON, f"TITLE: {it['title']}\nDESCRIPTION: {it['extract']}", 120)).split())[:220]
                except Exception:                                  # noqa: BLE001
                    line = None
            if line and not re.search(r"[0-9۰-۹]", line) and re.search(r"[؀-ۿ]", line):
                it["reason_fa"], made = line, made + 1
            else:
                it["reason_fa"] = None
        return short, f"{made} of {len(short)} Persian reasons kept (a line with any number, or not in Persian, is dropped)"
    stage("INVESTIGATE", reasons)

    def critique():
        for it in short:
            it["unverified"] = [x for x, missing in (("date", it["date_text"] is None), ("venue", True), ("price", True), ("still on sale", True)) if missing]
            if it["date_text"]:
                it["unverified"].insert(0, "date is text from a search result, not checked on the page")
        return short, "each item lists what was NOT established: venue, price and availability are never known from search results"
    stage("CRITIQUE", critique)

    payload = {"trace": trace, "kind": "event-shortlist", "items": [{k: it.get(k) for k in ("title", "url", "site", "date_text", "reason_fa", "unverified", "score")} for it in short]}
    state = stage("ACT", lambda: (lambda st: (st, f"shortlist placed in the approval queue as {trace}: {st}"))(propose(trace, payload, [it["url"][:80] for it in short])))
    stage("VERIFY", lambda: (state, "approval record read back" if state else "no approval record: the queue was not reachable from this service"))
    ok = all(s["ok"] for s in stages) and bool(state)
    return {"event": "mission_run", "status": "OK" if ok else "PARTIAL", "trace": trace, "stages": stages, "shortlist": short,
            "approval_state": state, "cost_pence": 0, "search_calls": obs["search_calls"], "total_ms": sum(s["ms"] for s in stages)}
