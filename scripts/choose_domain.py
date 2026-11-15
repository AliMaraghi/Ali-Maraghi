#!/usr/bin/env python3
"""Narrow domain routing scaffold (mission 2026-11-15, Phase 7). Produces a question, not a
build - see docs/ACTIVE_SYSTEM.md. Owner-gated: choosing the domain is the one thing in this
whole mission that genuinely cannot be synthesized, because it is a preference about the
owner's own real life, not a technical fact."""
import sys


def main():
    sys.stdout.write(
        "ACTIVE DOMAIN SELECTION:\n"
        "[1] Email Management (Requires IMAP/SMTP access)\n"
        "[2] Bill Processing (Requires PDF parsing + Bank API)\n"
        "[3] Calendar Optimization (Requires Google Calendar OAuth)\n"
        "Select the ONE domain to activate for the next 21 days: "
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
