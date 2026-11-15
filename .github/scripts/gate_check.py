#!/usr/bin/env python3
"""Persistent scheduling layer, S3 (brutal-honesty directive, 2026-11-15): the gate script
GitHub Actions calls on every PR, push to main, and nightly.

HARD BOUNDARY, checked first and unconditionally: refuses (exit 1, never a warning) if
runtime/ exists anywhere in the checkout - this is the one thing standing between a CI run
and a real-data leak (a real owner ESPP file, a real ledger, anything under FINANCE/MEDICAL
data classes). GitHub Actions checks out a FRESH clone every run; runtime/ should never
exist there at all unless something has gone wrong (a gitignore failure, a cache restore
gone wrong, a misconfigured workflow step) - this check exists to catch exactly that.

Then runs exactly the three named tests that prove the protected behaviours a regression
in any one of them must fail the workflow for: (1) an always_allow-classified proposal can
never reach ActionGateway.execute() / a ledger write, (2) synthetic disclosure is present
every session (never cached, never silently dropped), (3) the kill switch enforces denial
in under 1 second. This script does not run the full suite - scripts/test_offline.py (run
separately in the workflow) does that; this script's only job is the three named,
regression-sensitive behaviours.
"""
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROTECTED_TESTS = (
    "tests.test_tiering.TieringNeverApprovesTests.test_always_allow_cannot_reach_ledger_write",
    "tests.test_dpif_v1.SyntheticDisclosureTests.test_synthetic_disclosure_present_each_session",
    "tests.test_dpif_v1.KillSwitchTests.test_kill_switch_under_1s",
)


def check_no_runtime_dir() -> bool:
    runtime_dir = ROOT / "runtime"
    if runtime_dir.exists():
        print(f"HARD FAIL: {runtime_dir} exists in this checkout - refusing to run "
              "(data-leak boundary, see .github/scripts/gate_check.py's own docstring)")
        return False
    print(f"OK: {runtime_dir} does not exist in this checkout")
    return True


def main() -> int:
    if not check_no_runtime_dir():
        return 1
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "core")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", *PROTECTED_TESTS, "-v"],
                            cwd=str(ROOT), env=env)
    if result.returncode != 0:
        print("HARD FAIL: at least one protected behaviour regressed (see test output above)")
        return 1
    print("OK: all three protected behaviours hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
