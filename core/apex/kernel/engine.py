"""A single bounded evidence review; candidates are input, not invented findings."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

from . import VERSION
from .schema import Case
from .evidence import inspect_evidence
from .critic import critique


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def code_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def evaluate(case: Case, workspace: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Evaluation time requires timezone")
    checks = [inspect_evidence(e, case.domain, workspace, now) for e in case.evidence]
    findings = critique(case, checks)
    return {
        "engine_version": VERSION, "case_id": case.id, "domain": case.domain,
        "engine_code_sha256": code_digest(),
        "input_sha256": hashlib.sha256(canonical(asdict(case)).encode()).hexdigest(),
        "evaluated_at": now.isoformat(),
        "status": "BLOCKED_PENDING_EVIDENCE" if findings else "READY_FOR_HUMAN_REVIEW",
        "problem_discovery": {"question": case.problem, "assumptions": case.assumptions,
                              "missing_evidence": sorted({x["code"] for x in findings})},
        "hypotheses": [asdict(h) for h in case.hypotheses],
        "claims": [asdict(c) for c in case.claims],
        "provenance": [asdict(e) for e in case.evidence],
        "hypothesis_origin": "OPERATOR_SUPPLIED_NOT_AUTONOMOUS_DISCOVERY",
        "diversity_limit": "Lexical checks cannot establish substantive causal independence.",
        "negative_space": {"neglected_need": case.neglected_need, "second_order_effect": case.second_order_effect,
                           "status": "UNTESTED_QUESTIONS"},
        "evidence_checks": checks,
        "critic": {"kind": "DETERMINISTIC_CHECKLIST", "findings": findings,
                   "unresolved_review": ["Check source authenticity and claim entailment manually.",
                                         "Check total cost, opportunity cost, rights and failure scenarios."]},
        "experiment": {"baseline": case.baseline, "smallest_test": case.smallest_test, "executed": False},
        "empirical_superiority_proven": False, "verified_demand": False,
        "api_calls": 0, "additional_paid_ai_gbp": 0, "additional_paid_ai_usd": 0,
        "actions_executed": [],
    }
