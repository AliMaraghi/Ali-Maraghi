"""A-2 Scientific Research: Planner -> Researcher -> Executor -> Critic.

Built after a severe incident this session: an unreviewed `swarm_worker.py` was found running as
a systemd service, calling the Anthropic API every 10 seconds forever with no budget cap and no
stop-switch. This agent is the corrected, safe version of that idea - same ambition (a multi-step
LLM pipeline that drafts something useful), built entirely inside the existing safety rails:

- Research uses ONLY the existing, owner-reviewed PubMed E-utilities fetcher (core/apex/pubmed.py)
  - a real public API, not a generic web search or scrape. No new source is added here.
- Every LLM call (Planner, Executor, Critic) reserves against the existing Budget circuit
  breaker BEFORE the call and settles after, with its own provider/sku ("anthropic",
  "research-pipeline-step"). Zero-budget-by-default still applies: nothing spends until an
  operator explicitly runs this file's --set-price-millipence / --set-daily-cap-pence once.
- Scheduled through the normal AgentRunner cycle (BaseAgent.min_interval_seconds), which already
  enforces the project's durable-stop kill switch on every run - this agent never bypasses it.
- The pipeline only ever PROPOSES a reviewable draft to the existing ApprovalBook (kind
  "research_brief_proposal", adapter=None i.e. local record only - see kernel/gateway.py's
  DEFAULT_KINDS). It never posts, publishes or sends the draft anywhere; a human approves or not.
- Topics come from an owner-edited file (runtime/inbox/research_topics.json), the same pattern
  A-5/A-8 already use for their inputs - never from a live, unauthenticated chat endpoint.

This agent needs more than AgentContext carries (a Budget to reserve against, a Ledger to mark a
topic as processed so it is never silently re-billed every cycle, and an injectable PubMed
transport for testing) - all three are constructor arguments, not new AgentContext fields, so
other agents are unaffected.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import pubmed
from .agents_runtime import AgentContext, AgentResult, BaseAgent, contract, evidence_id
from .kernel.budget import Budget, BudgetDenied

KEY_FILE = Path("/etc/apex/anthropic-key")
MODEL = "claude-haiku-5-5"
PROVIDER, SKU = "anthropic", "research-pipeline-step"
MAX_SUBQUESTIONS = 3
MAX_REVISIONS = 1                       # Critic may send the draft back to Executor at most once
MANIFESTO_TONE = ("Decision support only, never presented as settled fact. State every "
                   "assumption. Every claim must be traceable to a specific piece of research "
                   "evidence actually returned below, or marked as the model's own inference.")


class ResearchPipelineError(RuntimeError):
    pass


def load_api_key() -> str:
    from . import local_llm
    if local_llm.enabled():
        return "local"                     # local Ollama model: no hosted key is read or needed
    if not KEY_FILE.is_file():
        raise ResearchPipelineError(f"{KEY_FILE} not found")
    if KEY_FILE.stat().st_mode & 0o777 & 0o077:
        raise ResearchPipelineError(f"{KEY_FILE} must not be group/world readable (chmod 600)")
    key = KEY_FILE.read_text().strip()
    if not key:
        raise ResearchPipelineError(f"{KEY_FILE} is empty")
    return key


def call_anthropic(api_key: str, system: str, user_text: str, max_tokens: int = 400) -> str:
    from . import local_llm
    if local_llm.enabled():
        # APEX_LLM_PROVIDER=ollama: same contract, served by the local model. The name of this
        # function is kept so every existing caller (and its budget reservation) is unchanged.
        try:
            return local_llm.complete(system, user_text, max_tokens)
        except local_llm.LocalLLMError as exc:
            raise ResearchPipelineError(str(exc)) from None
    # FOUND LIVE 2026-11-13, via a real call against api.anthropic.com (not a mock): claude-haiku-5-5
    # emits an internal "thinking" content block first by default, and at the max_tokens values
    # used throughout this project (80-150, sized for a short reply) the ENTIRE budget was
    # consumed by thinking with none left for visible text - content[0] was a thinking block, not
    # text, so every caller (A-2, Twitter drafts, finance strategy, dating) was silently raising
    # UPSTREAM_BAD_RESPONSE in production despite passing 550/550 offline (mocked) tests. None of
    # these four use cases need extended reasoning, so thinking is disabled outright, and the
    # content-block search below no longer assumes index 0 even so (defense in depth).
    payload = json.dumps({"model": MODEL, "max_tokens": max_tokens, "system": system,
                           "thinking": {"type": "disabled"},
                           "messages": [{"role": "user", "content": user_text}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload,
                                  headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                                           "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise ResearchPipelineError(f"UPSTREAM_ERROR:{exc.code}") from None
    except urllib.error.URLError:
        raise ResearchPipelineError("UPSTREAM_UNREACHABLE") from None
    try:
        blocks = data["content"]
        text_block = next((b for b in blocks if b.get("type") == "text"), None)
        if text_block is None:
            raise ResearchPipelineError("UPSTREAM_BAD_RESPONSE:NO_TEXT_BLOCK")
        return text_block["text"]
    except (KeyError, IndexError, TypeError):
        raise ResearchPipelineError("UPSTREAM_BAD_RESPONSE") from None


class ScientificResearch(BaseAgent):
    agent_id = "A-2"
    min_interval_seconds = 24 * 3600        # a multi-call LLM pipeline; deliberately conservative
    data_classes = ("public",)

    def __init__(self, budget: Budget, ledger, transport=None, limiter=None):
        self.budget = budget
        self.ledger = ledger
        self.transport = transport or pubmed.live_transport
        self.limiter = limiter or pubmed.limiter_for(None)

    def _spend(self, key: str, system: str, user_text: str, max_tokens: int = 400) -> str:
        self.budget.reserve(key, "core", PROVIDER, SKU, 1)
        try:
            api_key = load_api_key()
            text = call_anthropic(api_key, system, user_text, max_tokens)
        except ResearchPipelineError:
            self.budget.release(key)
            raise
        self.budget.settle(key, 1)
        return text

    def _research(self, subquestion: str) -> list:
        try:
            result = pubmed.search(subquestion, self.transport, self.limiter, retmax=3)
            pmids = result.get("pmids", [])
            if not pmids:
                return []
            fetched = pubmed.fetch_records(time.strftime("%Y-%m-%d"), self.transport, self.limiter, pmids=pmids)
            # title is wrap_untrusted()'d external text (agent_contract.py): data, never instructions.
            return [{"pmid": r["pmid"], "title": r["title"].get("content", "")} for r in fetched["records"]]
        except Exception:
            return []          # a research dead-end is evidence of nothing, not a pipeline failure

    def run(self, ctx: AgentContext) -> AgentResult:
        topics_path = ctx.inbox / "research_topics.json"
        risks = ["Decision support only; a draft here is not vetted, fact-checked prose - the owner must review it",
                 "Evidence is limited to PubMed abstracts; absence of a PubMed hit does not mean a claim is false"]
        if not topics_path.is_file():
            return AgentResult(contract(self.agent_id, f"A2-{ctx.today}", [], risks,
                                        [f"Missing owner-supplied file: {topics_path.name}. Add [{{\"topic\": \"...\", \"status\": \"pending\"}}]"],
                                        0.0, []))
        topics = json.loads(topics_path.read_text(encoding="utf-8"))
        if not isinstance(topics, list):
            raise ValueError("research_topics.json must be a JSON list")
        pending = next((t for t in topics if isinstance(t, dict) and t.get("status") == "pending"
                        and isinstance(t.get("topic"), str) and t["topic"].strip()), None)
        if pending is None:
            return AgentResult(contract(self.agent_id, f"A2-{ctx.today}", [], risks,
                                        ["No pending topic in research_topics.json (all processed, or none added yet)"], 0.0, []))

        topic = pending["topic"].strip()
        run_id = f"{self.agent_id}.{int(ctx.now)}"
        cost_units = 0
        try:
            plan_text = self._spend(f"{run_id}.plan", MANIFESTO_TONE,
                                     f"Break this research topic into at most {MAX_SUBQUESTIONS} short, concrete sub-questions, "
                                     f"one per line, no numbering, no commentary: {topic}", max_tokens=150)
            cost_units += 1
            subquestions = [line.strip("-* ").strip() for line in plan_text.splitlines() if line.strip()][:MAX_SUBQUESTIONS]

            evidence = []
            for sq in subquestions:
                evidence.extend(self._research(sq))
            evidence_text = "\n".join(f"PMID {e['pmid']}: {e['title']}" for e in evidence) or "(no PubMed results found for any sub-question)"

            draft = self._spend(f"{run_id}.draft", MANIFESTO_TONE,
                                 f"Topic: {topic}\nSub-questions: {subquestions}\nEvidence found:\n{evidence_text}\n\n"
                                 f"Write a brief (under 150 words) synthesising only what the evidence above actually supports. "
                                 f"If the evidence is thin or absent, say so plainly instead of filling the gap.")
            cost_units += 1

            verdict, notes, revisions_done = "APPROVE", "", 0
            while True:
                critic_text = self._spend(f"{run_id}.critic.{cost_units}", MANIFESTO_TONE,
                                           f"Review this draft against the evidence. Evidence:\n{evidence_text}\n\nDraft:\n{draft}\n\n"
                                           f"Reply with exactly 'APPROVE' on its own if every claim is traceable to the evidence or "
                                           f"clearly marked as inference; otherwise reply 'REVISE: <one-line reason>'.", max_tokens=80)
                cost_units += 1
                if critic_text.strip().upper().startswith("APPROVE"):
                    verdict, notes = "APPROVE", critic_text.strip()
                    break
                verdict, notes = "REVISE_REQUESTED", critic_text.strip()
                if revisions_done >= MAX_REVISIONS:
                    break          # give up asking for further revisions; ship the last draft, verdict stays REVISE_REQUESTED
                draft = self._spend(f"{run_id}.revise.{cost_units}", MANIFESTO_TONE,
                                     f"Revise this draft to address: {notes}\nEvidence:\n{evidence_text}\n\nOriginal draft:\n{draft}",
                                     max_tokens=200)
                cost_units += 1
                revisions_done += 1
        except (BudgetDenied, ResearchPipelineError) as exc:
            return AgentResult(contract(self.agent_id, f"A2-{ctx.today}", [], risks,
                                        [f"Pipeline stopped before completion: {type(exc).__name__}:{exc}"], 0.0, []))

        draft, notes = draft[:2000], notes[:2000]       # bound to kernel.gateway.MAX_TEXT so a verbose LLM reply can't fail submission
        eid = evidence_id("research", topic + run_id)
        claims = [{"text": f"Draft brief on '{topic}' ({verdict}, {len(evidence)} PubMed source(s)): {draft}",
                   "kind": "inference", "evidence_ids": [eid]}]

        pending["status"] = "proposed"
        topics_path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

        return AgentResult(
            contract(self.agent_id, f"A2-{ctx.today}", claims, risks, [] if evidence else ["No PubMed evidence was found for this topic"],
                     0.6 if evidence else 0.2, [eid], cost_pence=0),
            proposals=[{"kind": "research_brief_proposal", "payload": {"topic": topic, "draft": draft, "critic_notes": notes},
                       "evidence_ids": [eid]}])


def set_price_and_cap(ledger_root: Path, price_millipence: int | None, cap_pence: int | None):
    from .kernel.memory import Ledger
    with Ledger(ledger_root) as ledger:
        budget = Budget(ledger)
        if price_millipence is not None:
            budget.set_price(PROVIDER, SKU, price_millipence, time.time(),
                              "flat per-LLM-step estimate, owner-set, not metered per-token")
            print(f"Price set: {price_millipence/1000}p/step for {PROVIDER}:{SKU}")
        if cap_pence is not None:
            budget.set_cap("core", "day", cap_pence)
            print(f"Daily cap set: {cap_pence}p/day on pool 'core' (shared with other core-pool spenders, e.g. voice_api.py)")


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="One-time setup: price and/or cap the research pipeline's spend.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--set-price-millipence", type=int, default=None)
    parser.add_argument("--set-daily-cap-pence", type=int, default=None)
    args = parser.parse_args()
    if args.set_price_millipence is None and args.set_daily_cap_pence is None:
        print("Nothing to do - pass --set-price-millipence and/or --set-daily-cap-pence.", file=sys.stderr)
        sys.exit(1)
    set_price_and_cap(args.root, args.set_price_millipence, args.set_daily_cap_pence)
