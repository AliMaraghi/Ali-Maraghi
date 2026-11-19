"""Self-directed tasks for the OS runner: openers for the top event (A-10), a devil's-advocate note on every
pending financial proposal (A-17), and a nightly critic that turns yesterday's weak outputs into short "lessons"
appended to tomorrow's prompts (A-18). The local model only words things; every result carries the data it used.
Lessons are bounded (5 lines, 160 chars), logged, reversible, and can never replace the base rules of a prompt."""
from __future__ import annotations

import json
import re
from pathlib import Path

MAX_LESSONS, LESSON_CHARS = 5, 160
BANNED = re.compile(r"ignore|disregard|previous instruction|system prompt|no need to|skip the (rule|check)|always approve", re.I)


def _json(llm, system: str, user: str, tokens: int = 350):
    if llm is None:
        return None
    try:
        raw = llm(system, user, tokens)
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:                                              # noqa: BLE001
        return None


# ---- lessons (A-18's only write surface) -------------------------------------------------------------------
def _lessons_path(root) -> Path:
    return Path(root) / "runtime" / "settings" / "prompt_lessons.json"


def lessons(root, task: str) -> list:
    try:
        return [x for x in json.loads(_lessons_path(root).read_text(encoding="utf-8")).get(task, []) if isinstance(x, str)][-MAX_LESSONS:]
    except (OSError, ValueError, AttributeError):
        return []


def with_lessons(root, task: str, system: str) -> str:
    extra = lessons(root, task)
    return system + ("\nLessons from review of earlier outputs (style only; the rules above always win):\n- " + "\n- ".join(extra) if extra else "")


def add_lesson(root, task: str, line: str) -> bool:
    line = " ".join(str(line).split())[:LESSON_CHARS]
    if len(line) < 12 or BANNED.search(line):
        return False
    path = _lessons_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if line in data.get(task, []):
        return False
    data[task] = (data.get(task, []) + [line])[-MAX_LESSONS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return True


# ---- A-10: three openers for the top picked event --------------------------------------------------------------
OPENERS = ("You write three different opening lines a man could say to someone at this specific event. Each must mention "
           "something from the event title, be under 18 words, playful and British, never about careers. "
           'Reply ONLY with JSON: {"openers": ["...", "...", "..."]}')


def energy(root, now: float | None = None) -> int | None:
    """The owner's own 1-5 energy setting from the dashboard; ignored once it is more than 12 hours old."""
    import time
    try:
        e = json.loads((Path(root) / "runtime" / "settings" / "energy.json").read_text(encoding="utf-8"))
        return int(e["level"]) if (now or time.time()) - float(e["at"]) < 12 * 3600 and 1 <= int(e["level"]) <= 5 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def social(root, llm, events: dict | None, mentions) -> dict:
    picked = (events or {}).get("picked") or []
    if not picked:
        return {"event": "social", "status": "NO_DATA", "detail": "The event scout has no picked event"}
    top = picked[0]
    level = energy(root)
    system = with_lessons(root, "social", OPENERS) + ("\nThe owner is low on energy today: each line under 10 words, easy to say." if level in (1, 2) else "")
    obj = _json(llm, system, f"EVENT: {top.get('title')}\nWHEN: {top.get('start')}")
    lines = [str(x)[:200] for x in (obj or {}).get("openers", []) if isinstance(x, str) and mentions(x, top.get("title", ""))][:3]
    return {"event": "social", "status": "OK" if lines else ("NO_MODEL" if llm is None else "NO_DATA"),
            "title": top.get("title"), "start": top.get("start"), "url": top.get("url"), "openers": lines, "energy_used": level}


# ---- A-17: argue against each pending proposal -------------------------------------------------------------
CRITIC = ("You are a sceptical reviewer. Given one proposed action, give the strongest honest case AGAINST doing it, using only "
          "the facts in the proposal. Do not invent numbers. "
          'Reply ONLY with JSON: {"against": "two sentences", "what_to_check": "one concrete thing to verify first"}')


def red_team(llm, proposals: list) -> dict:
    notes = []
    for p in proposals[:5]:
        obj = _json(llm, CRITIC, f"PROPOSAL KIND: {p['kind']}\nPROPOSAL: {p['payload'][:1500]}")
        if obj and isinstance(obj.get("against"), str):
            notes.append({"proposal_id": p["id"], "kind": p["kind"], "against": obj["against"][:400],
                          "what_to_check": str(obj.get("what_to_check", ""))[:200]})
    return {"event": "critic", "status": "OK" if notes else ("NO_MODEL" if llm is None else "NO_DATA"), "reviewed": len(proposals[:5]), "notes": notes}


# ---- A-18: nightly review -> lessons ---------------------------------------------------------------------
REVIEW = ("You review one output written by an assistant. Judge it against the task. "
          'Reply ONLY with JSON: {"useful": true|false, "problem": "short, or empty", '
          '"lesson": "one short style instruction that would have prevented the problem, or empty"}')


def evolve(root, llm, outputs: dict) -> dict:
    """outputs: {task: [text, ...]} from the last day. Adds at most one lesson per task; reports exactly what changed."""
    reviewed, changes, verdicts = 0, [], []
    for task, texts in outputs.items():
        for text in texts[:3]:
            obj = _json(llm, REVIEW, f"TASK: {task}\nOUTPUT: {text[:600]}", 200)
            if not obj:
                continue
            reviewed += 1
            verdicts.append({"task": task, "useful": bool(obj.get("useful")), "problem": str(obj.get("problem", ""))[:160]})
            lesson = obj.get("lesson")
            if not obj.get("useful") and isinstance(lesson, str) and add_lesson(root, task, lesson):
                changes.append({"task": task, "lesson_added": " ".join(lesson.split())[:LESSON_CHARS]})
                break
    return {"event": "evolution", "status": "OK" if reviewed else ("NO_MODEL" if llm is None else "NO_DATA"),
            "reviewed": reviewed, "judged_useful": sum(1 for v in verdicts if v["useful"]), "verdicts": verdicts[:12], "changes": changes}
