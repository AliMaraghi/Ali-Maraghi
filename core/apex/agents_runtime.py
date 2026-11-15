"""Agent runtime: BaseAgent, AgentContext and AgentRunner. Agents PROPOSE; only the Action Gateway (with human approval) can act.

A run: data-class isolation check -> agent.run(ctx) -> Universal Agent Contract validation (agent_id must match) -> each proposal is submitted to the Gateway as a typed, evidence-bearing PENDING proposal
(daily limit and deferral are enforced by ApprovalBook) -> the run is written to the hash-chained journal -> an optional notifier is told (link-only Telegram notice). Nothing here executes an action,
calls a paid API, sends mail or contacts a person. Errors in one agent never stop the others, and exception text is never recorded (class name only).
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import agents_governing as governing
from .agent_contract import ContractError, parse_output
from .kernel import tiering
from .kernel.policy import enforce_durable_stop
from .kernel.schema import identifier


@dataclass
class AgentContext:
    now: float
    today: str                              # YYYY-MM-DD supplied by the caller
    inbox: Path                             # owner-provided input files (never fetched from the internet by the agent)
    rules: Path                             # owner-provided, SOURCED rule tables
    fetch: Callable[[str], bytes] | None = None      # injectable public-feed fetcher (None = no network)
    config: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    contract: dict                          # a Universal Agent Contract payload
    proposals: list = field(default_factory=list)    # [{"kind","payload","evidence_ids"}]


class BaseAgent:
    agent_id = ""
    data_classes = ("public",)
    min_interval_seconds = 0          # 0 = may run every cycle; set per agent so cheap/free agents are not re-run needlessly often

    def run(self, ctx: AgentContext) -> AgentResult:          # pragma: no cover - abstract
        raise NotImplementedError


def contract(agent_id, task_id, claims, risks, unknowns, confidence, evidence, contradictions=(), cost_pence=0):
    return {"task_id": task_id, "agent_id": agent_id, "claims": claims, "risks": list(risks), "unknowns": list(unknowns),
            "confidence": confidence, "evidence": sorted(set(evidence)), "contradictions": list(contradictions), "estimated_cost_pence": cost_pence}


def evidence_id(prefix, text):
    return f"{prefix}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


class AgentRunner:
    def __init__(self, ledger, gateway, agents, notifier=None, clock=time.time):
        self.ledger, self.gateway, self.agents, self.notifier, self.clock = ledger, gateway, list(agents), notifier, clock
        ledger.db.execute("CREATE TABLE IF NOT EXISTS agent_schedule (agent_id TEXT PRIMARY KEY, last_run REAL NOT NULL)")

    def _due(self, agent_id, interval):
        if interval <= 0:
            return True
        row = self.ledger.db.execute("SELECT last_run FROM agent_schedule WHERE agent_id=?", (agent_id,)).fetchone()
        return row is None or self.clock() - row[0] >= interval

    def _mark_run(self, agent_id):
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT INTO agent_schedule (agent_id, last_run) VALUES (?,?) "
                                   "ON CONFLICT(agent_id) DO UPDATE SET last_run=excluded.last_run", (agent_id, self.clock()))

    def run_once(self, ctx: AgentContext):
        summaries = []
        for agent in self.agents:
            summaries.append(self._run_agent(agent, ctx))
        return summaries

    def _run_agent(self, agent, ctx):
        spec = governing.get(agent.agent_id)
        summary = {"agent": agent.agent_id, "name": spec.name, "status": "OK", "proposals": [], "notified": 0}
        try:
            enforce_durable_stop(self.ledger)
            if spec.status != governing.IMPLEMENTED_LOCAL:
                raise PermissionError("SPEC_ONLY")
            if not self._due(agent.agent_id, agent.min_interval_seconds):
                summary["status"] = "SKIPPED_TOO_SOON"
                return summary
            self._mark_run(agent.agent_id)   # marked as soon as it is attempted, so a later failure is not retried every cycle either
            governing.check_inputs(agent.agent_id, agent.data_classes)
            result = agent.run(ctx)
            out = parse_output(result.contract)
            if out.agent_id != agent.agent_id:
                raise ContractError("agent_id mismatch")
            summary.update(confidence=out.confidence, claims=len(out.claims), unknowns=list(out.unknowns), risks=list(out.risks))
            for item in result.proposals:
                pid = identifier(f"{agent.agent_id}-{hashlib.sha256(repr(sorted(item['payload'].items())).encode()).hexdigest()[:14]}")
                try:
                    state = self.gateway.submit(pid, spec.domain, item["kind"], f"agent:{agent.agent_id}", item["payload"], item["evidence_ids"])
                except sqlite3.IntegrityError:
                    state = "DUPLICATE"
                tier = None
                if state in ("PENDING", "DEFERRED"):
                    decision = tiering.tier_for(item["kind"], self.gateway.kinds.get(item["kind"]))
                    tiering.journal_decision(self.ledger, pid, spec.domain, decision)
                    tier = decision.tier
                summary["proposals"].append({"id": pid, "state": state, "tier": tier})
                if state == "PENDING" and self.notifier is not None:
                    try:
                        self.notifier(pid, item["kind"])
                        summary["notified"] += 1
                    except Exception as exc:                 # a notice failure must never lose the proposal
                        summary["notice_error"] = type(exc).__name__
        except Exception as exc:
            summary.update(status="ERROR", error=type(exc).__name__)
        with self.ledger.transaction():
            self.ledger._append(identifier(f"agentrun.{agent.agent_id}.{int(self.clock())}"[:80]), "decision", spec.domain,
                                {"event": "agent_run", "agent": agent.agent_id, "status": summary["status"], "error": summary.get("error"),
                                 "confidence": summary.get("confidence"), "claims": summary.get("claims"),
                                 "proposals": [p["id"] for p in summary["proposals"]]})
        return summary
