#!/usr/bin/env bash
# Owner-triggered only - never runs automatically, never scheduled. Prints today's
# row template for docs/a10_3week_log.md and asks the owner to fill it, then appends
# it themselves (this script does not edit the file for them - the owner's own
# numbers belong in the owner's own hands).
set -euo pipefail

TODAY="$(date +%Y-%m-%d)"

cat <<EOF
Today's row for docs/a10_3week_log.md (fill in the blanks, then paste this
line into the table yourself):

| $TODAY | <messages sent today> | <replies> | <conversations> | <meetings booked> | <one-line note> |

This script does not append anything automatically - the owner decides
when and whether to log, per docs/ACTIVE_SYSTEM.md.
EOF
