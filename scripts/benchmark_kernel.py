"""Replay frozen author-separated synthetic policy fixtures against a simple rule.

This does not measure ChatGPT, Claude, Codex or independent real-world outcomes.
The implementing agent read these cases before wiring the runner; they cannot
be reused as unseen cases for subsequent versions.
"""
from pathlib import Path
import hashlib
import json
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.kernel.lab import Trial, compare
from apex.kernel.policy import Action, Policy, KillState
FROZEN_SHA256 = "3477cf88aecafff06b92940038622bef0fa4e561a669951e8497592ce9e27b72"


def candidate(payload):
    try:
        return Policy(payload["policy_domain"], KillState(payload["kill_state"])).authorize(Action(**payload["action"]))[0]
    except (ValueError, TypeError, KeyError):
        return False


def baseline(payload):
    action = payload["action"]
    return action.get("kind") == "record_decision" and action.get("estimated_pence") == 0


def conventional_checklist(payload):
    """Straightforward standalone specification checklist, with no agent engine."""
    action = payload["action"]
    return (payload["policy_domain"] in {"opportunity", "studio", "personal"}
            and payload["kill_state"] in {"RUNNING", "DISABLE_EGRESS", "REVOKE_CREDENTIALS"}
            and isinstance(action["idempotency_key"], str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", action["idempotency_key"]) is not None
            and action["domain"] == payload["policy_domain"]
            and action["sensitivity"] in {"public", "synthetic"}
            and action["kind"] == "record_decision"
            and type(action["estimated_pence"]) is int and action["estimated_pence"] == 0)


def benchmark():
    path = ROOT / "reports/validation/kernel_holdout_cases.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_SHA256:
        raise ValueError("Frozen benchmark fixtures changed; create a separately versioned evaluation")
    data = json.loads(raw)
    trials = tuple(Trial(**row) for row in data["policy_cases"])
    receipt = compare("kernel-policy-v1", candidate, "baseline", baseline, trials)
    checklist = compare("kernel-policy-v1", candidate, "conventional-checklist", conventional_checklist, trials)
    return {"receipt": receipt.to_dict(), "fixture_file_sha256": hashlib.sha256(raw).hexdigest(),
            "conventional_checklist_comparison": checklist.to_dict(),
            "cases": [{"id": t.id, "expected": t.expected, "candidate": candidate(t.payload), "baseline": baseline(t.payload)} for t in trials],
            "scope": data["scope"], "limitations": data["limitations"] + [__doc__],
            "paid_api_spend_gbp": 0, "paid_api_spend_usd": 0, "external_calls": 0,
            "real_world_superiority": "NOT_TESTED", "candidate_promoted": False}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2, allow_nan=False))
