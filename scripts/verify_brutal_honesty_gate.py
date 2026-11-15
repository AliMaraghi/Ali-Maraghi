#!/usr/bin/env python3
"""Single offline entry point for exactly the four areas this round's brutal-honesty
directive (2026-11-15, section 4.3) is about: the sandbox (Phase F), the Financial
Intelligence planner->generator->evaluator harness, the Gateway/approval-tiering policy
layer, and data-class isolation. It does not replace scripts/test_offline.py (the full
repo suite); it exists so a reviewer - or the pre-commit gate in section 5 - can get one
honest, scoped answer about exactly these invariants without wading through the full
suite. It imports and runs existing tests only; it duplicates none of them.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/verify_brutal_honesty_gate.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["PYTHONPATH"] = str(ROOT / "core")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# (module filename, [TestCase class names to include - empty list means "the whole file"])
SCOPE = [
    ("test_sandbox.py", []),                                              # Phase F: sandbox
    ("test_tiering.py", []),                                              # approval tiering
    ("test_agents_runtime.py", ["FinancialTests", "RosterTests"]),         # A-8 harness + isolation
    ("test_propose_capability.py", ["ProposeCapabilityTests"]),           # sandbox wired into proposals
]


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    loader, suite = unittest.TestLoader(), unittest.TestSuite()
    covered = []
    for filename, class_names in SCOPE:
        module = _load(ROOT / "tests" / filename)
        if not class_names:
            suite.addTests(loader.loadTestsFromModule(module))
            covered.append(filename)
            continue
        for name in class_names:
            suite.addTests(loader.loadTestsFromTestCase(getattr(module, name)))
            covered.append(f"{filename}::{name}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "scope": "SANDBOX_HARNESS_GATEWAY_ISOLATION_ONLY_NOT_THE_FULL_SUITE",
        "covered": covered,
        "tests_run": result.testsRun,
        "passed": result.testsRun - len(result.skipped) - len(result.failures) - len(result.errors),
        "skipped": len(result.skipped), "failures": len(result.failures), "errors": len(result.errors),
    }
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
