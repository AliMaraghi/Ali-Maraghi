"""Six-gate venture tracker. The system does the desk work for the current gate (a short brief built from the owner's
own description plus any live public-tender evidence it could fetch), then STOPS and waits for the owner. Only the
owner's approval moves a venture to the next gate. State lives in runtime/settings/ventures.json."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

GATES = ["DISCOVER", "VALIDATE", "BUILD", "LAUNCH", "ACQUIRE", "SCALE"]
ASK = {
    "DISCOVER": "Who exactly would pay for this, what do they pay for it today, and what is the smallest version that could be sold this month?",
    "VALIDATE": "List five named kinds of buyer to contact this week, the one-paragraph offer to send them, and what reply would count as proof of demand.",
    "BUILD": "List only what must exist before the first paid job (documents, tools, registrations), each with who does it and whether it costs money.",
    "LAUNCH": "Write the first-week plan: day by day, what is sent to whom, and the single number that decides whether to continue.",
    "ACQUIRE": "Describe a repeatable way to get the next ten clients using what worked for the first, and what it costs per client in time.",
    "SCALE": "State what would have to be true to double revenue without doubling the owner's hours, and the first hire or tool that unlocks it.",
}
SYSTEM = ("{identity}\nYou are preparing one gate of a venture plan for the owner. Use ONLY the owner's description and the "
          "evidence lines given. Never invent prices, buyers or statistics: where a number is needed and not in the evidence, "
          "write 'unverified - check'. Be concrete and brief. Reply ONLY with JSON: "
          '{{"brief": ["4 to 6 short lines"], "do_this_week": ["up to 3 actions"], "missing": ["facts you could not source"]}}')


def identity() -> str:
    base = Path(__file__).parent / "identity"
    try:
        return (base / "soul.md").read_text(encoding="utf-8") + "\n" + (base / "rules.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def _path(root) -> Path:
    return Path(root) / "runtime" / "settings" / "ventures.json"


def load(root) -> list:
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(root, ventures: list) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ventures[-10:], ensure_ascii=False), encoding="utf-8")


def create(root, name: str, description: str, now: float | None = None) -> dict:
    name, description = " ".join(name.split())[:80], description.strip()[:1500]
    if len(name) < 3 or len(description) < 20:
        raise ValueError("name and a description of at least 20 characters are required")
    ventures = load(root)
    v = {"id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] + f"-{int(now or time.time()) % 100000}",
         "name": name, "description": description, "gate": "DISCOVER", "status": "WORKING", "briefs": {}, "history": []}
    ventures.append(v)
    _save(root, ventures)
    return v


def decide(root, venture_id: str, approve: bool, note: str = "", now: float | None = None) -> dict:
    """The owner's decision on the current gate. Approve -> next gate; decline -> the same gate is redone with his note."""
    ventures = load(root)
    v = next((x for x in ventures if x["id"] == venture_id), None)
    if v is None or v["status"] != "WAITING_OWNER":
        raise ValueError("no gate is waiting for a decision on that venture")
    v["history"].append({"gate": v["gate"], "approved": bool(approve), "note": note.strip()[:300], "at": now or time.time()})
    if approve and v["gate"] == GATES[-1]:
        v["status"] = "COMPLETE"
    elif approve:
        v["gate"], v["status"] = GATES[GATES.index(v["gate"]) + 1], "WORKING"
    else:
        v["status"] = "WORKING"
        v["briefs"].pop(v["gate"], None)
    _save(root, ventures)
    return v


def tender_evidence(fetch_json, keywords: list, days: int = 14, today=None) -> dict:
    """Live UK public tenders (Contracts Finder) whose title or description mentions one of the keywords."""
    from datetime import date, timedelta
    from .sources import contracts_finder
    end = today or date.today()
    try:
        data = fetch_json(contracts_finder.search_url((end - timedelta(days=days)).isoformat(), end.isoformat()))
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "ERROR", "detail": type(exc).__name__, "lines": []}
    lines = []
    for rel in (data.get("releases") or []) if isinstance(data, dict) else []:
        tender = rel.get("tender") or {}
        text = f"{tender.get('title', '')} {tender.get('description', '')}".lower()
        if any(k in text for k in keywords):
            value = (tender.get("value") or {}).get("amount")
            lines.append(f"Tender: {str(tender.get('title'))[:120]} | buyer: {str((rel.get('buyer') or {}).get('name'))[:80]}"
                         f" | value: {value if value is not None else 'not stated'} | id: {str(rel.get('id'))[:60]}")
    return {"status": "OK", "checked": len((data.get("releases") or []) if isinstance(data, dict) else []), "lines": lines[:8]}


def work(root, llm, fetch_json=None) -> list:
    """Draft the current gate for every venture that is WORKING. Returns one action line per venture touched."""
    ventures, done = load(root), []
    for v in ventures:
        if v["status"] != "WORKING" or v["gate"] in v["briefs"]:
            continue
        keywords = [w for w in re.findall(r"[a-z]{5,}", (v["name"] + " " + v["description"]).lower())][:12]
        evidence = tender_evidence(fetch_json, keywords) if fetch_json and v["gate"] in ("DISCOVER", "VALIDATE") else {"status": "NOT_USED", "lines": []}
        last_note = next((h["note"] for h in reversed(v["history"]) if h["gate"] == v["gate"] and not h["approved"] and h["note"]), "")
        obj = None
        if llm is not None:
            try:
                raw = llm(SYSTEM.format(identity=identity()),
                          f"VENTURE: {v['name']}\nOWNER'S DESCRIPTION: {v['description']}\nGATE: {v['gate']}\nQUESTION: {ASK[v['gate']]}\n"
                          f"EVIDENCE:\n" + ("\n".join(evidence["lines"]) or "none") + (f"\nOWNER'S NOTE ON THE LAST DRAFT: {last_note}" if last_note else ""), 500)
                obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            except Exception:                                      # noqa: BLE001
                obj = None
        if not isinstance(obj, dict) or not isinstance(obj.get("brief"), list):
            done.append({"task": f"venture:{v['id']}", "result": "NO_MODEL" if llm is None else "NO_DATA", "detail": f"gate {v['gate']} not drafted"})
            continue
        v["briefs"][v["gate"]] = {"brief": [str(x)[:300] for x in obj["brief"][:6]], "do_this_week": [str(x)[:200] for x in (obj.get("do_this_week") or [])[:3]],
                                  "missing": [str(x)[:200] for x in (obj.get("missing") or [])[:5]], "evidence": evidence, "at": time.time()}
        v["status"] = "WAITING_OWNER"
        done.append({"task": f"venture:{v['id']}", "result": "OK", "detail": f"gate {v['gate']} drafted; waiting for your decision (tender evidence: {evidence['status']}, {len(evidence['lines'])} match)"})
    if done:
        _save(root, ventures)
    return done
