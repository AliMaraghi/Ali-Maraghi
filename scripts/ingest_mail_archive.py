#!/usr/bin/env python3
"""Build the persona's voice samples from a Google Takeout mail archive (.mbox). Read-only, offline.

  python3 -B scripts/ingest_mail_archive.py /path/to/All\\ mail.mbox --owner you@gmail.com [--owner other@x] [--since 2012]

Prints counts only - never message content. See core/apex/persona_ingest.py for what is kept.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex import persona_ingest, persona_twin              # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mbox")
    parser.add_argument("--owner", action="append", required=True, help="an address you send from; repeat for each")
    parser.add_argument("--since", type=int, default=2012)
    parser.add_argument("--samples", type=int, default=60)
    args = parser.parse_args()
    path = Path(args.mbox)
    if not path.is_file():
        print(json.dumps({"status": "NOT_FOUND", "path": str(path)}))
        return 1
    red_lines = persona_twin.load_profile(ROOT).never_disclose
    stats, samples = persona_ingest.analyse(path, set(args.owner), args.since, max(1, min(args.samples, 200)), red_lines)
    persona_ingest.write_outputs(ROOT, stats, samples)
    print(json.dumps({"status": "OK", **{k: stats[k] for k in ("messages_in_archive", "sent_by_owner_used", "by_year", "by_language", "samples_kept")}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
