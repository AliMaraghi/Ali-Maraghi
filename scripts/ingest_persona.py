#!/usr/bin/env python3
"""Build the persona's voice samples from your own archives. Read-only, offline, prints counts only.

  Mail (Google Takeout .mbox):
    python3 -B scripts/ingest_persona.py mail  "/path/All mail.mbox" --owner you@gmail.com [--owner other@x]
  Chats (WhatsApp "Export chat" .txt/.zip, Instagram/Facebook message JSON; a file or a whole folder):
    python3 -B scripts/ingest_persona.py chats /path/to/folder --name "Your Name" [--name "Other spelling"]

Only what YOU wrote is read. See core/apex/persona_ingest.py for what is kept and what is skipped.
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
    parser.add_argument("kind", choices=("mail", "chats"))
    parser.add_argument("path")
    parser.add_argument("--owner", action="append", default=[], help="mail: an address you send from; repeatable")
    parser.add_argument("--name", action="append", default=[], help="chats: your display name exactly as in the export; repeatable")
    parser.add_argument("--since", type=int, default=2012)
    parser.add_argument("--samples", type=int, default=60)
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(json.dumps({"status": "NOT_FOUND", "path": str(path)}))
        return 1
    red_lines = persona_twin.load_profile(ROOT).never_disclose
    limit = max(1, min(args.samples, 200))
    try:
        if args.kind == "mail":
            stats, samples = persona_ingest.analyse(path, set(args.owner), args.since, limit, red_lines)
            persona_ingest.write_outputs(ROOT, stats, samples)
        else:
            stats, samples = persona_ingest.analyse_chats(path, set(args.name), args.since, limit, red_lines)
            persona_ingest.write_chat_outputs(ROOT, stats, samples)
    except ValueError as exc:
        print(json.dumps({"status": "BAD_INPUT", "detail": str(exc)}))
        return 1
    print(json.dumps({"status": "OK", **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
