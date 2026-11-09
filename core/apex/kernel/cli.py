"""Run from the development workspace: PYTHONPATH=core python -m apex.kernel.cli."""
import argparse
from pathlib import Path
import json
import sys
import sqlite3

from .schema import Case, strict_json
from .evidence import read_local
from .engine import evaluate
from .memory import Ledger
from .policy import Action, Policy, KillState


def main(argv=None):
    parser = argparse.ArgumentParser(description="APEX local public/synthetic evidence review; zero external actions")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review")
    review.add_argument("input", help="Relative case JSON path within development workspace")
    review.add_argument("--record", action="store_true", help="Persist result in local runtime ledger")
    review.add_argument("--key", help="Required idempotency key when recording")
    review.add_argument("--kill-state", choices=[x.value for x in KillState], default="RUNNING")
    history = sub.add_parser("history")
    history.add_argument("--domain", choices=["opportunity", "studio", "personal"], required=True)
    args = parser.parse_args(argv)
    # Determined by installed source, never by a research document or environment variable.
    root = Path(__file__).resolve().parents[3]
    try:
        if args.command == "history":
            with Ledger(root) as ledger:
                print(json.dumps(ledger.records(args.domain), indent=2, ensure_ascii=True))
            return 0
        case = Case.parse(strict_json(read_local(root, args.input, 262144).decode("utf-8")))
        result = evaluate(case, root)
        if args.record:
            if not args.key:
                raise ValueError("Recording requires an explicit idempotency key")
            policy = Policy(case.domain, KillState(args.kill_state))
            action = Action(args.key, "record_decision", case.domain)
            allowed, reason = policy.authorize(action)
            if not allowed:
                raise PermissionError(reason)
            with Ledger(root) as ledger:
                # Exclude wall-clock evaluation time from retry identity, but retain first evaluation.
                for event in ledger.records(case.domain):
                    if event["key"] == args.key and event["payload"].get("input_sha256") == result["input_sha256"]:
                        previous = event["payload"]
                        comparable = dict(result, evaluated_at=previous["evaluated_at"])
                        result = comparable
                result["ledger_seq"] = policy.record(ledger, action, result)
        print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 0 if result["status"] == "READY_FOR_HUMAN_REVIEW" else 2
    except (ValueError, TypeError, KeyError, OSError, PermissionError, RecursionError, sqlite3.Error) as error:
        print(json.dumps({"status": "BLOCKED_INVALID_INPUT_OR_POLICY", "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
