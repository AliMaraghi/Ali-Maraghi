#!/usr/bin/env python3
"""Applies owner-approved evolution proposals, tests them, and commits the result locally.

Off unless ENABLE_EVOLUTION_SANDBOX=true. Run as the repository owner (never root). It does
not push: the root-owned apex-autopush timer uploads commits after its privacy scan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.evolution import apply_approved, config              # noqa: E402
from apex.kernel.memory import Ledger                          # noqa: E402
from apex.kernel.policy import enforce_durable_stop            # noqa: E402

TARGET = "core/apex/evolution/target_heuristics.py"


def run_tests() -> bool:
    proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_persona_and_evolution", "tests.test_content_engine"],
                          cwd=ROOT, env={"PYTHONPATH": str(ROOT / "core"), "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
                          capture_output=True, timeout=300)
    return proc.returncode == 0


def main() -> int:
    if not config.enabled():
        print(json.dumps({"status": "DISABLED", "flag": config.FLAG}))
        return 0
    results = {}
    with Ledger(ROOT) as ledger:
        enforce_durable_stop(ledger)
        for proposal_id in apply_approved.pending_approved(ledger):
            outcome = apply_approved.apply_one(ledger, proposal_id, run_tests)
            results[proposal_id] = outcome
            if outcome == "APPLIED":
                subprocess.run(["git", "add", TARGET], cwd=ROOT, check=False)
                subprocess.run(["git", "-c", "user.name=APEX", "-c", "user.email=apex@localhost", "commit", "-q", "-m",
                                f"Apply owner-approved evolution proposal {proposal_id}"], cwd=ROOT, check=False)
    print(json.dumps({"status": "OK", "results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
