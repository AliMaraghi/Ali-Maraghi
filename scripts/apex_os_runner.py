#!/usr/bin/env python3
"""APEX OS runner: one real cycle of "look, judge, act, report", repeated in the background.

Each cycle (1) measures how stale every data source is against how often it should refresh (prediction error),
(2) gives every one of the 18 roster agents an honest state with its reason, (3) ranks what to do by expected
utility from the owner's own approve/decline record, (4) does the work that needs no owner input (public trend scan,
script drafts on the local model, refreshing overdue scouts), and (5) writes the whole result to the ledger.
It never publishes, pays, sends or deploys. Runs as a thread inside apex-voice, or standalone:
  python3 -B scripts/apex_os_runner.py --once | --loop
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from apex import priority, scout_common, trend_scout          # noqa: E402

INTERVAL = 900
EXPECTED = {"events": 4 * 3600, "wealth": 4 * 3600, "commute": 4 * 3600, "adult": 4 * 3600, "trends": 6 * 3600,
            "spend": 14 * 86400, "content_drafts": 24 * 3600, "property": 7 * 86400,
            "listings": 24 * 3600, "event_links": 12 * 3600, "social": 12 * 3600, "critic": 24 * 3600, "evolution": 24 * 3600, "graph": 6 * 3600}
CREDENTIAL = {"A-5": "Reed job-search key", "A-6": "Gmail connection (sync is switched off)"}
VALUE = {"trends": 3.0, "content_drafts": 4.0, "events": 5.0, "wealth": 6.0, "commute": 2.0, "adult": 3.0, "spend": 6.0}


def _fresh(root, name, label):
    rec = scout_common.latest(root, name)
    if not rec:
        return "NEVER_RUN", f"{label}: no run recorded yet"
    if rec.get("status") not in (None, "OK"):
        return "ERROR", f"{label}: last run {rec.get('status')}"
    return "AUTONOMOUS_SCAN", f"{label}: last run {time.strftime('%d %b %H:%M', time.gmtime(rec['generated_at']))} UTC"


def _a4(root):
    from apex import people_graph
    s = people_graph.summary(root)
    return ("AUTONOMOUS_SCAN", f"People graph: {s['people']} people, {s['companies']} companies (LinkedIn export)") if s else \
        ("BLOCKED_MISSING_INPUT", "No people data: upload a LinkedIn connections export")


def _a6(root):
    return "BLOCKED_MISSING_CREDENTIAL", "Google is authorised again, but the Gmail sync still fails; needs the server diagnose report to fix"


def _a14(root):
    """Real self-check: private files must not be readable by other users on the server."""
    bad, fixed = [], []
    for rel in ("runtime", "runtime/inbox"):                       # private folders: close them to other users, then re-check
        p = root / rel
        try:
            if p.is_dir() and p.stat().st_mode & 0o077:
                os.chmod(p, 0o700)
                fixed.append(rel)
        except OSError:
            pass
    for rel in ("runtime", "runtime/inbox", "runtime/kernel.sqlite3", "runtime/inbox/reed-api-key", "runtime/inbox/people.json"):
        p = root / rel
        if p.exists() and p.stat().st_mode & 0o077:
            bad.append(rel)
    return ("ERROR", "Readable by other server users: " + ", ".join(bad)) if bad else ("AUTONOMOUS_SCAN", "File-permission check passed on private runtime files" + (f"; closed to other users just now: {', '.join(fixed)}" if fixed else ""))


def _a17(root):
    try:
        st = json.loads((root / "runtime" / "e2e_last.json").read_text())
        return ("AUTONOMOUS_SCAN" if st.get("state") == "passed" else "ERROR"), f"End-to-end system test: {st.get('state')}"
    except Exception:                                              # noqa: BLE001
        return "NEVER_RUN", "End-to-end test result not found"


def _a18(root):
    if not (root / "runtime" / "settings" / "evolution_on").is_file():
        return "BLOCKED_MISSING_INPUT", "Evolution lab is switched off"
    try:
        db = _db(root)
        row = db.execute("SELECT decision, recorded_at FROM evolution_log ORDER BY id DESC LIMIT 1").fetchone()
        db.close()
    except sqlite3.Error:
        row = None
    return ("AUTONOMOUS_SCAN", f"Evolution lab: last result {row[0]}") if row else ("NEVER_RUN", "Evolution lab is on; first daily run has not happened yet")


def _a18b(root):
    rec = scout_common.latest(root, "evolution")
    lab = _a18(root)
    if rec:
        return "AUTONOMOUS_SCAN", f"Nightly review: {rec.get('reviewed', 0)} output(s) judged, {len(rec.get('changes', []))} lesson(s) added; lab: {lab[1]}"
    return lab


SUBSYSTEM = {"A-10": lambda r: _fresh(r, "social", "Openers for the top event"), "A-4": _a4, "A-6": _a6, "A-7": lambda r: _fresh(r, "wealth", "Wealth and jobs scout"), "A-11": lambda r: _fresh(r, "content_drafts", "Trend scripts"),
             "A-14": _a14, "A-16": lambda r: _fresh(r, "spend", "Spending and behaviour patterns"), "A-17": lambda r: _fresh(r, "critic", "Devil's-advocate notes on pending proposals") if scout_common.latest(r, "critic") else _a17(r), "A-18": _a18b}


def _db(root: Path):
    return sqlite3.connect((root / "runtime" / "kernel.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=5)


def approval_counts(root: Path) -> dict:
    """{proposer: [approved_or_executed, declined]} and pending count, from the real proposals table."""
    counts, pending = {}, []
    try:
        db = _db(root)
        for proposer, kind, state, pid in db.execute("SELECT proposer, kind, state, id FROM proposals"):
            c = counts.setdefault(proposer, [0, 0])
            if state in ("APPROVED", "EXECUTED"):
                c[0] += 1
            elif state in ("DENIED", "DECLINED"):
                c[1] += 1
            elif state == "PENDING":
                pending.append({"id": pid, "kind": kind, "proposer": proposer})
        db.close()
    except sqlite3.Error:
        pass
    return {"counts": counts, "pending": pending}


def source_gaps(root: Path, now: float) -> list:
    gaps = []
    for name, expected in EXPECTED.items():
        rec = scout_common.latest(root, name)
        age = now - rec["generated_at"] if rec and rec.get("generated_at") else None
        if rec and rec.get("status") in ("NO_DATA", "NO_MODEL", "ERROR") and age is not None:
            age = max(age, expected + age * 4)                     # a failed run does not count as fresh: retry about hourly
        gaps.append({"source": name, "age_seconds": round(age) if age is not None else None, "expected_seconds": expected,
                     "surprise": priority.surprise(age, expected)})
    return sorted(gaps, key=lambda g: -g["surprise"])


def agent_states(root: Path, approvals: dict) -> list:
    """All 18 roster agents. States: AUTONOMOUS_SCAN, PENDING_APPROVAL, BLOCKED_MISSING_INPUT, BLOCKED_MISSING_CREDENTIAL,
    ERROR, NEVER_RUN, NOT_BUILT. Every non-running state carries the reason."""
    import orchestrator
    from apex import agents_governing, scout_wealth
    telemetry = {a["agent_id"]: a for a in orchestrator.agent_telemetry(root)}
    pending_by = {}
    for p in approvals["pending"]:
        pending_by.setdefault(p["proposer"], []).append(p["id"])
    roster = [(r[0], r[1]) for r in getattr(agents_governing, "_ROLES", [])] or [(k, v["name"]) for k, v in orchestrator._AGENT_META.items()]
    out = []
    for agent_id, name in roster:
        t = telemetry.get(agent_id)
        waiting = [pid for proposer, ids in pending_by.items() if proposer == f"agent:{agent_id}" for pid in ids]
        if agent_id == "A-10" and (t is None or t["blocked"]):
            state, reason = SUBSYSTEM["A-10"](root)
        elif t is None and agent_id in SUBSYSTEM:
            state, reason = SUBSYSTEM[agent_id](root)
        elif t is None:
            state, reason = "NOT_BUILT", "Specified in the manifesto; no running code yet"
        elif agent_id == "A-5" and scout_wealth.reed_key() is None:
            state, reason = "BLOCKED_MISSING_CREDENTIAL", CREDENTIAL["A-5"]
        elif t["blocked"]:
            state, reason = "BLOCKED_MISSING_INPUT", t["current_task"]
        elif waiting:
            state, reason = "PENDING_APPROVAL", f"{len(waiting)} item(s) waiting for your decision"
        elif t["status"] == "ERROR":
            state, reason = "ERROR", str(t.get("last_error") or "last run failed")[:200]
        elif t["status"] == "NEVER_RUN":
            state, reason = "NEVER_RUN", "Has its input but the agents service has not run it yet"
        else:
            state, reason = "AUTONOMOUS_SCAN", t["current_task"]
        out.append({"agent_id": agent_id, "name": name, "state": state, "reason": reason,
                    "last_run_at": t.get("last_run_at") if t else None})
    return out


def plan(gaps: list, approvals: dict, pulls: dict) -> list:
    """Rank the refreshable sources: expected utility (value x P(owner finds it useful) x urgency) plus a UCB bonus."""
    all_ok = sum(c[0] for c in approvals["counts"].values())
    all_no = sum(c[1] for c in approvals["counts"].values())
    p = priority.posterior(all_ok, all_no)
    total = sum(pulls.values()) or 1
    ranked = []
    for g in gaps:
        eu = priority.expected_utility(VALUE.get(g["source"], 1.0) * (1 + g["surprise"]), p, 0, 0.1)
        bonus = priority.ucb(0.0, pulls.get(g["source"], 0), total)
        ranked.append({"task": g["source"], "expected_utility": round(eu, 2), "explore_bonus": None if bonus == float("inf") else round(bonus, 2),
                       "due": g["surprise"] > 0})
    return sorted(ranked, key=lambda r: (-(r["explore_bonus"] is None), -(r["expected_utility"] + (r["explore_bonus"] or 0))))


def _local_llm():
    try:
        from apex import local_llm
        return (lambda s, u, m: local_llm.complete(s, u, max_tokens=m)) if local_llm.enabled() else None
    except Exception:                                              # noqa: BLE001
        return None


def cycle(root: Path = ROOT, now: float | None = None, fetch=None, llm="auto", run_scouts=True) -> dict:
    from apex.kernel.memory import Ledger
    from apex.kernel.policy import enforce_durable_stop
    now = time.time() if now is None else now
    actions = []
    if (root / "runtime" / "kernel.sqlite3").is_file():            # never write to a database that cannot be read
        db = _db(root)
        try:
            db.execute("SELECT COUNT(*) FROM events").fetchone()
        finally:
            db.close()
    approvals = approval_counts(root)
    gaps = source_gaps(root, now)
    due = {g["source"] for g in gaps if g["surprise"] > 0}
    if fetch is None:
        import agents_runner
        fetch = agents_runner.fetch_public
    llm = _local_llm() if llm == "auto" else llm
    with Ledger(root) as ledger:
        enforce_durable_stop(ledger)                               # the owner's kill switch stops this loop too
    # Network and model work happens with the database CLOSED; it is opened only for the instant of each write.
    from apex import l5
    to_record, trends = [], None
    if "trends" in due:
        trends = trend_scout.scan(fetch)
        to_record.append(("trends", trends))
        actions.append({"task": "trends", "result": trends["status"], "detail": f"{trends['count']} terms, failed feeds: {trends['feeds_failed'] or 'none'}"})
    if "content_drafts" in due:
        trends = trends or scout_common.latest(root, "trends") or {}
        drafts = [d for d in (trend_scout.draft(llm, t, l5.lessons(root, 'content')) for t in (trends.get("top") or [])[:2]) if d]
        status = "OK" if drafts else ("NO_MODEL" if llm is None else "NO_DATA")
        to_record.append(("content_drafts", {"event": "content_drafts", "status": status, "drafts": drafts}))
        actions.append({"task": "content_drafts", "result": status, "detail": f"{len(drafts)} draft(s) stored for your review; nothing is published"})
    if "social" in due:
        from apex import scout_events
        soc = l5.social(root, llm, scout_common.latest(root, "events"), scout_events.mentions_event)
        to_record.append(("social", soc))
        actions.append({"task": "social", "result": soc["status"], "detail": f"{len(soc.get('openers', []))} opener(s) for: {soc.get('title') or soc.get('detail')}"})
    if "critic" in due:
        pend = []
        try:
            db = _db(root)
            pend = [{"id": r[0], "kind": r[1], "payload": r[2]} for r in db.execute("SELECT id, kind, payload FROM proposals WHERE state = 'PENDING' AND domain != 'studio' LIMIT 5")]
            db.close()
        except sqlite3.Error:
            pass
        crit = l5.red_team(llm, pend) if pend else {"event": "critic", "status": "OK", "reviewed": 0, "notes": []}
        to_record.append(("critic", crit))
        actions.append({"task": "critic", "result": crit["status"], "detail": f"argued against {len(crit['notes'])} of {len(pend)} pending proposal(s)"})
    if "evolution" in due and time.gmtime(now).tm_hour in (2, 3, 4):   # nightly, after 02:00 UTC
        outs = {}
        dr = scout_common.latest(root, "content_drafts") or {}
        outs["content"] = [d["hook"] + " | " + " / ".join(d["beats"]) for d in dr.get("drafts", [])]
        so = scout_common.latest(root, "social") or {}
        outs["social"] = list(so.get("openers", []))
        evo = l5.evolve(root, llm, {k: v for k, v in outs.items() if v})
        to_record.append(("evolution", evo))
        actions.append({"task": "evolution", "result": evo["status"], "detail": f"reviewed {evo['reviewed']}, lessons added: {len(evo['changes'])}"})
    if "listings" in due:
        from apex import brave_search
        bkey = brave_search.load_key(root)
        within = (scout_common.latest(root, "property") or {}).get("within_budget") or []
        if not bkey:
            lst = {"event": "listings", "status": "BLOCKED_MISSING_CREDENTIAL", "detail": "Brave search key not set (Research box on the dashboard)", "links": []}
        else:
            links, errs = [], []
            for borough in within[:3]:
                try:
                    for r in brave_search.search(root, bkey, "property", f"3 bedroom house with garden for sale {borough} under 450000"):
                        links.append({"borough": borough, "title": r["title"], "url": r["url"], "site": r["domain"], "extract": r["extract"][:200]})
                    time.sleep(1.2)
                except Exception as exc:                           # noqa: BLE001
                    errs.append(f"{borough}:{type(exc).__name__}")
            lst = {"event": "listings", "status": "OK" if links else "NO_DATA", "links": links[:9], "errors": errs,
                   "note": "Search-engine links to portal pages; prices and availability are whatever the page shows when you open it."}
        to_record.append(("listings", lst))
        actions.append({"task": "listings", "result": lst["status"], "detail": lst.get("detail") or f"{len(lst['links'])} link(s)"})
    try:                                                           # ventures: draft the current gate, then wait for the owner
        from apex import venture
        from apex.sources import contracts_finder
        actions.extend(venture.work(root, llm, lambda url: json.loads(contracts_finder.fetch_page(url))))
    except Exception as exc:                                       # noqa: BLE001
        actions.append({"task": "venture", "result": "ERROR", "detail": f"{type(exc).__name__}: {str(exc)[:100]}"})
    if "event_links" in due:
        from apex import brave_search
        bkey = brave_search.load_key(root)
        if not bkey:
            ev = {"event": "event_links", "status": "BLOCKED_MISSING_CREDENTIAL", "detail": "Brave search key not set", "links": []}
        else:
            import re as _re
            single = _re.compile(r"eventbrite\.co\.uk/e/|ra\.co/events/\d|dice\.fm/event/|designmynight\.com/london/.+/.+|feverup\.com/m/\d")
            banned = _re.compile(r"teen|kids|child|family|toddler|school|online|virtual|webinar|course|workshop", _re.I)
            when = _re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+\d{1,2}\s+[A-Z][a-z]{2,8}|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+20\d\d)?", _re.I)
            month = time.strftime("%B %Y", time.gmtime(now))
            links, errs, seen, dropped = [], [], set(), 0
            for q in (f"London gala tickets {month}", f"London members club party tickets {month}", f"London warehouse party tickets {month}",
                      f"London wine tasting evening tickets {month}", f"London supper club tickets {month}"):
                try:
                    for r in brave_search.search(root, bkey, "events", q):
                        text = r["title"] + " " + r["extract"]
                        if r["url"] in seen or not single.search(r["url"]) or banned.search(text):
                            dropped += 1                           # category pages and non-events are not offered as events
                            continue
                        seen.add(r["url"])
                        found = when.search(text)
                        links.append({"query": q, "title": r["title"], "url": r["url"], "site": r["domain"], "extract": r["extract"][:160],
                                      "date_text": found.group(0) if found else None})
                    time.sleep(1.2)
                except Exception as exc:                           # noqa: BLE001
                    errs.append(f"{q[:20]}:{type(exc).__name__}")
            links.sort(key=lambda l: l["date_text"] is None)
            ev = {"event": "event_links", "status": "OK" if links else "NO_DATA", "links": links[:12], "errors": errs, "dropped_not_single_events": dropped,
                  "note": "Single-event pages only. The date shown is text from the search result and is not verified; open the page to confirm date, venue and price."}
        to_record.append(("event_links", ev))
        actions.append({"task": "event_links", "result": ev["status"], "detail": ev.get("detail") or f"{len(ev['links'])} link(s), errors: {ev.get('errors') or 'none'}"})
    if "graph" in due:
        try:
            from apex import knowledge_graph, people_graph
            try:
                jobs = json.loads((root / "runtime" / "inbox" / "jobs.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                jobs = []
            g = knowledge_graph.rebuild(root, people_graph.load(root), jobs if isinstance(jobs, list) else [],
                                        (scout_common.latest(root, "events") or {}).get("picked") or [],
                                        (scout_common.latest(root, "trends") or {}).get("top") or [],
                                        (scout_common.latest(root, "property") or {}).get("rows") or [])
            to_record.append(("graph", {"event": "graph", "status": "OK", **g}))
            actions.append({"task": "graph", "result": "OK", "detail": f"{g['entities']} entities, {g['edges']} edges, {len(g['links'])} cross-link(s)"})
        except Exception as exc:                                   # noqa: BLE001
            actions.append({"task": "graph", "result": "ERROR", "detail": f"{type(exc).__name__}: {str(exc)[:100]}"})
    try:                                                           # A-2: keep one research topic queued each day
        topics_file = root / "runtime" / "inbox" / "research_topics.json"
        topics = json.loads(topics_file.read_text(encoding="utf-8")) if topics_file.is_file() else []
        topics = topics if isinstance(topics, list) else []
        stamp = root / "runtime" / "settings" / "research_seed_last"
        if not any(isinstance(t, dict) and t.get("status") == "pending" for t in topics) and \
                (not stamp.is_file() or now - float(stamp.read_text() or 0) > 23 * 3600):
            seeds = ["AI adoption in public sector procurement", "executive function strategies for adults with ADHD",
                     "first-time home buyer financial stress", "remote work second job burnout"]
            topics.append({"topic": seeds[int(now // 86400) % len(seeds)], "status": "pending"})
            topics_file.parent.mkdir(parents=True, exist_ok=True)
            topics_file.write_text(json.dumps(topics[-50:]), encoding="utf-8")
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(str(now))
            actions.append({"task": "research_seed", "result": "OK", "detail": f"queued for A-2: {topics[-1]['topic']}"})
    except (OSError, ValueError) as exc:
        actions.append({"task": "research_seed", "result": "ERROR", "detail": type(exc).__name__})
    if "property" in due:
        from apex import property_scout
        prop = property_scout.run(fetch)
        to_record.append(("property", prop))
        actions.append({"task": "property", "result": prop["status"], "detail": f"{len(prop.get('rows', []))} borough(s), month {prop.get('month')}, failed: {prop.get('feeds_failed') or 'none'}"})
    if to_record:
        with Ledger(root) as ledger:
            for name, body in to_record:
                scout_common.record(ledger, name, body, now)
    new_drafts = next((b["drafts"] for n, b in to_record if n == "content_drafts"), [])
    if new_drafts:                                                 # queue each draft for the owner's decision
        try:
            import hashlib
            import run_autonomous_agent
            with Ledger(root) as ledger:
                book = run_autonomous_agent.approval_book(ledger)
                if book is None:
                    actions.append({"task": "approval_queue", "result": "BLOCKED_MISSING_CREDENTIAL",
                                    "detail": "This service cannot read the approvals secret, so drafts are shown here but not queued"})
                else:
                    for d in new_drafts:
                        pid = "draft-" + hashlib.sha256((d["term"] + d["hook"]).encode()).hexdigest()[:16]
                        book.propose(pid, "studio", "content-draft", "agent:A-11", d, [f"trend:{d['term']}"[:80]])
                    actions.append({"task": "approval_queue", "result": "OK", "detail": f"{len(new_drafts)} draft(s) queued for your approval"})
        except Exception as exc:                                   # noqa: BLE001
            actions.append({"task": "approval_queue", "result": "ERROR", "detail": f"{type(exc).__name__}: {str(exc)[:120]}"})
    if run_scouts:
        try:                                                       # feed the job agent: Reed listings -> runtime/inbox/jobs.json
            from apex import scout_wealth
            jobs_file = root / "runtime" / "inbox" / "jobs.json"
            key = scout_wealth.reed_key()
            if key and (not jobs_file.is_file() or now - jobs_file.stat().st_mtime > 6 * 3600):
                import run_scouts as rs
                cfg = scout_common.load_config(root)
                results = scout_wealth.reed_fetch(key, cfg["job_keywords"], cfg["job_location"])
                rs._collect_jobs(results)
                actions.append({"task": "jobs", "result": "OK" if results else "NO_DATA", "detail": f"{len(results)} Reed listing(s) for '{cfg['job_keywords']}' passed to the job agent"})
        except Exception as exc:                                   # noqa: BLE001
            actions.append({"task": "jobs", "result": "ERROR", "detail": f"{type(exc).__name__}: {str(exc)[:120]}"})
    if run_scouts and {"events", "wealth"} & due and all(g["surprise"] >= 0.5 for g in gaps if g["source"] in ("events", "wealth")):
        try:                                                       # the 4-hourly timer is late: run the scouts now
            out = subprocess.run([sys.executable, "-B", str(root / "scripts" / "run_scouts.py")], cwd=root, timeout=600,
                                 capture_output=True, text=True, env=dict(os.environ))
            actions.append({"task": "scouts", "result": "OK" if out.returncode == 0 else "ERROR", "detail": (out.stdout or out.stderr).strip()[-200:]})
        except Exception as exc:                                   # noqa: BLE001
            actions.append({"task": "scouts", "result": "ERROR", "detail": type(exc).__name__})
    pulls = {}
    try:
        db = _db(root)
        for name in EXPECTED:
            pulls[name] = db.execute("SELECT COUNT(*) FROM events WHERE event_key LIKE ?", (f"scout.{name}.%",)).fetchone()[0]
        db.close()
    except sqlite3.Error:
        pass
    agents = agent_states(root, approvals)
    from apex import metacognition
    final_gaps = source_gaps(root, now)
    evo = scout_common.latest(root, "evolution") or {}
    meta = {"confidence": metacognition.confidence(final_gaps, agents, actions),
            "curriculum": metacognition.curriculum(final_gaps, agents, actions, scout_common.latest(root, "property"), len(evo.get("changes", [])))}
    day = time.strftime("%Y%m%d", time.gmtime(now))
    eve = scout_common.latest(root, "evening")
    if time.gmtime(now).tm_hour >= 18 and not (eve and eve.get("day") == day):
        ran, bad = {}, {}
        try:
            db = _db(root)
            for (raw,) in db.execute("SELECT payload FROM events WHERE event_key LIKE ?", (f"scout.os.{day}.%",)):
                for a in json.loads(raw).get("actions", []):
                    bucket = ran if a["result"] == "OK" else bad
                    bucket[a["task"]] = bucket.get(a["task"], 0) + 1
            db.close()
        except (sqlite3.Error, ValueError):
            pass
        for a in actions:
            bucket = ran if a["result"] == "OK" else bad
            bucket[a["task"]] = bucket.get(a["task"], 0) + 1
        with Ledger(root) as ledger:
            scout_common.record(ledger, "evening", {"event": "evening", "status": "OK", "day": day, "succeeded": ran, "did_not_succeed": bad,
                                                    "waiting_for_owner": [c["task"] for c in meta["curriculum"] if c["who"] == "owner"],
                                                    "tomorrow": [c["task"] for c in meta["curriculum"] if c["who"] == "system"]}, now)
    payload = {"event": "os_cycle", "status": "OK", "meta": meta, "agents": agents, "gaps": source_gaps(root, now), "plan": plan(gaps, approvals, pulls),
               "actions": actions, "pending_approvals": approvals["pending"][:50], "pending_total": len(approvals["pending"]),
               "summary": {s: sum(1 for a in agents if a["state"] == s) for s in sorted({a["state"] for a in agents})}}
    with Ledger(root) as ledger:
        scout_common.record(ledger, "os", payload, now)
    return payload


def loop(root: Path = ROOT, interval: int = INTERVAL) -> None:
    """Each cycle runs in its own short-lived process (like the scout and briefing timers), never inside the web service."""
    time.sleep(30)
    while True:
        try:
            out = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--once"], cwd=root, timeout=1500,
                                 capture_output=True, text=True, env=dict(os.environ))
            print(f"[os] cycle exit={out.returncode} {(out.stderr or out.stdout).strip()[-200:]}", flush=True)
        except Exception as exc:                                   # noqa: BLE001 - logged, loop survives
            print(f"[os] cycle failed: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        loop()
    else:
        result = cycle()
        print(json.dumps(result["summary"]), [a["task"] + ":" + a["result"] for a in result["actions"]])
