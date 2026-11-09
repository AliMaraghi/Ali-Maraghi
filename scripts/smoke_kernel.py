"""Verify CLI persistence across separate processes using only a synthetic case."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.kernel.engine import code_digest
from apex.kernel.memory import Ledger


def main():
    key = "smoke-" + code_digest()[:24]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "core"), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-B", "-m", "apex.kernel.cli", "review",
               "examples/evidence_review_synthetic.json", "--record", "--key", key]
    runs = []
    for _ in range(2):
        execution = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
        result = json.loads(execution.stdout)
        if execution.returncode != 2 or result["status"] != "BLOCKED_PENDING_EVIDENCE":
            raise RuntimeError("Synthetic input did not remain blocked")
        runs.append({"returncode": execution.returncode, "status": result["status"],
                     "ledger_seq": result["ledger_seq"], "input_sha256": result["input_sha256"],
                     "engine_code_sha256": result["engine_code_sha256"]})
    if runs[0] != runs[1]:
        raise RuntimeError("Process-restart idempotency failed")
    with Ledger(ROOT) as ledger:
        records = ledger.records("opportunity")
        matching = [r for r in records if r["key"] == key]
        if len(matching) != 1 or ledger.records("studio"):
            raise RuntimeError("Unexpected record count or domain leakage")
        summary = {"key": key, "runs": runs, "ledger_integrity_events": ledger.verify(),
                   "records_for_this_key": len(matching), "studio_records": 0,
                   "scope": "SYNTHETIC_CLI_PROCESS_RESTART_SMOKE_NOT_REAL_WORLD_VALUE"}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
