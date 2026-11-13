#!/usr/bin/env python3
"""Record what actually happened after a fact/recommendation - the real prerequisite for any
future calibration. Nothing infers this automatically from a voice utterance (that would mean
guessing intent from ambiguous speech); it is always this explicit, deliberate owner action.

Usage:
  python3 scripts/record_outcome.py --list                       # see recent facts and their ids
  python3 scripts/record_outcome.py --fact-id 3 --outcome accepted --note "sold the shares"

Outcomes: accepted, rejected, acted_on, ignored.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import facts as factstore  # noqa: E402
from apex.kernel.memory import Ledger        # noqa: E402


def list_recent_facts(ledger, limit: int = 20) -> list:
    factstore._ensure_facts_table(ledger)
    rows = ledger.db.execute(
        "SELECT id, subject, predicate, object, source, asserted_at FROM facts "
        "ORDER BY asserted_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r[0], "subject": r[1], "predicate": r[2], "object": r[3], "source": r[4], "asserted_at": r[5]} for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="Show the most recent facts and their ids")
    parser.add_argument("--fact-id", type=int, default=None)
    parser.add_argument("--outcome", choices=("accepted", "rejected", "acted_on", "ignored"), default=None)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    with Ledger(ROOT) as ledger:
        if args.list:
            for row in list_recent_facts(ledger):
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["asserted_at"]))
                print(f"[{row['id']}] {when}  {row['subject']}/{row['predicate']} ({row['source']}): {row['object'][:90]}")
            return
        if args.fact_id is None or args.outcome is None:
            sys.exit("Pass --list to see fact ids, or --fact-id N --outcome {accepted,rejected,acted_on,ignored} [--note TEXT]")
        factstore.record_outcome(ledger, args.fact_id, args.outcome, args.note)
        print(f"Recorded: fact {args.fact_id} -> {args.outcome}" + (f" ({args.note})" if args.note else ""))


if __name__ == "__main__":
    main()
