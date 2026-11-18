"""Content drafts in the owner's voice, queued for approval. Publishes nothing.

One run: pick an owner-supplied topic and the best-scoring content angle (weights live in
evolution/target_heuristics.py, so approved evolution changes take effect here), ask the local
model for a draft with the persona style in its system prompt, pass it through the
Constitutional Critic with at most two redrafts, and file ONE `external-post` proposal for the
owner to approve, edit or discard. A draft the critic still rejects is dropped, not queued.

Topics come from runtime/inbox/content_topics.json: [{"topic": "...", "channel": "linkedin"}].
Off unless ENABLE_AUTONOMOUS_SOCIAL=true. No posting connector exists: approval records the
decision, and the owner posts the text.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from . import persona_twin, social_pacing
from .evolution import target_heuristics
from .kernel.budget import BudgetDenied

POOL, PROVIDER, SKU = "studio", "anthropic", "content-draft"
PROPOSER = "agent:content-engine"
ANGLE_BRIEFS = {
    "personal_story": "Tell it as something that happened to you, in the first person, with one concrete detail.",
    "analysis": "Explain what is going on and why it matters, with one specific fact or number you were given.",
    "contrarian": "Take a view most people in the field would push back on, and say plainly why you hold it.",
    "how_to": "Give the reader two or three practical steps they could do this week.",
}
MAX_TOPICS, MAX_WORDS = 50, 180


def load_topics(root: Path) -> list[dict]:
    path = Path(root) / "runtime" / "inbox" / "content_topics.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 200_000:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("topic"), str) and 3 <= len(item["topic"].strip()) <= 300:
            out.append({"topic": item["topic"].strip(), "channel": str(item.get("channel", "linkedin"))[:30].lower()})
    return out[:MAX_TOPICS]


def pick_angle() -> str:
    return max(sorted(ANGLE_BRIEFS), key=target_heuristics.score_angle)


def _used(ledger) -> set[str]:
    if not ledger.db.execute("SELECT 1 FROM sqlite_master WHERE name='proposals'").fetchone():
        return set()
    return {r[0] for r in ledger.db.execute("SELECT id FROM proposals WHERE proposer=?", (PROPOSER,))}


def run_once(root: Path, ledger, book, budget, llm: Callable[[str, str, int], str], now: float | None = None) -> dict:
    if not social_pacing.enabled():
        return {"status": "DISABLED", "flag": social_pacing.FLAG}
    now = time.time() if now is None else now
    topics, used = load_topics(root), _used(ledger)
    todo = [t for t in topics if "post." + hashlib.sha256((t["topic"] + t["channel"]).encode()).hexdigest()[:16] not in used]
    if not todo:
        return {"status": "NO_TOPICS", "detail": "add topics to runtime/inbox/content_topics.json" if not topics else "every topic already has a draft"}
    item = todo[0]
    proposal_id = "post." + hashlib.sha256((item["topic"] + item["channel"]).encode()).hexdigest()[:16]
    profile, angle = persona_twin.load_profile(root), pick_angle()
    system = (persona_twin.system_context(profile) + f"\nWrite one {item['channel']} post of at most {MAX_WORDS} words. "
              + ANGLE_BRIEFS[angle] + " Use only facts given in the topic; invent no numbers, names or events. "
              "Return the post text only.")
    calls = [0]

    def ask(user_text: str) -> str:
        key = f"{proposal_id}.{calls[0]}"
        budget.reserve(key, POOL, PROVIDER, SKU, 1)
        calls[0] += 1
        try:
            text = llm(system, user_text, 400)
        except Exception:
            budget.release(key)
            raise
        budget.settle(key, 1)
        return str(text).strip()

    try:
        draft = ask("Topic: " + item["topic"])
        text, verdict, rounds = persona_twin.rewrite_until_pass(
            draft, profile, lambda current, brief: ask(f"Topic: {item['topic']}\n\nRewrite this draft. Fix: {brief}\n\nDraft:\n{current}"),
            channel=item["channel"], mode="draft")
    except BudgetDenied as exc:
        return {"status": "BUDGET", "detail": str(exc)[:120]}
    except Exception as exc:
        return {"status": "MODEL_FAILED", "detail": type(exc).__name__}
    if verdict.status != "PASS":
        return {"status": f"DROPPED_{verdict.status}", "rounds": rounds, "findings": [f.rule for f in verdict.findings][:8]}
    state = book.propose(proposal_id, "studio", "external-post", PROPOSER,
                         {"text": text, "channel": item["channel"], "angle": angle, "topic": item["topic"], "delivery": "owner-posts"},
                         [f"topic:{proposal_id}"], commentary=f"Draft for {item['channel']} ({angle.replace('_', ' ')}), {rounds} redraft(s).")
    return {"status": f"PROPOSED_{state}", "proposal_id": proposal_id, "angle": angle, "rounds": rounds, "model_calls": calls[0]}
