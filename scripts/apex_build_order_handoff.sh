#!/usr/bin/env bash
# Owner handoff (brutal-honesty directive, 2026-11-15, V3). Collapses the scattered
# per-session owner-gated command list into ONE script the owner runs on the personal
# machine. Runs on macOS or Linux without modification (uses only POSIX/bash + python3).
#
# H3 and H4 touch real data (a real owner ESPP/tax file, a real console approval). This
# script NEVER executes those automatically - it prints the exact command and PAUSES for
# the owner to run it themselves in another terminal, then continues.
#
# Usage:
#   bash scripts/apex_build_order_handoff.sh            # real run
#   bash scripts/apex_build_order_handoff.sh --dry-run  # no real files, no real decisions, no pauses
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE="$(date -u +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)"
LOG="$ROOT/APEX_SESSIONS/owner_handoff_${DATE}.log"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

mkdir -p "$ROOT/APEX_SESSIONS"
: > "$LOG"

log() { printf '%s\n' "$1" | tee -a "$LOG"; }
section() { log ""; log "=== $1 ==="; }

pause() {
  if [ "$DRY_RUN" = "1" ]; then
    log "[dry-run] (would pause for Enter here)"
    return 0
  fi
  read -r -p "Press Enter to continue... " _ignored
}

ask() {
  # ask "question" -> prints the question, reads a line, logs both
  local question="$1" answer
  if [ "$DRY_RUN" = "1" ]; then
    log "[dry-run] Q: $question"
    log "[dry-run] A: (skipped, no real input in --dry-run)"
    return 0
  fi
  log "Q: $question"
  read -r -p "> " answer
  log "A: $answer"
}

section "Prerequisites"
if command -v python3 >/dev/null 2>&1; then
  log "python3: present ($(python3 --version 2>&1))"
else
  log "python3: MISSING - install it before continuing"
  [ "$DRY_RUN" = "0" ] && exit 1
fi

BROWSER_FOUND=0
for b in google-chrome chromium chromium-browser firefox safari open; do
  command -v "$b" >/dev/null 2>&1 && BROWSER_FOUND=1 && log "browser helper found: $b"
done
if [ "$BROWSER_FOUND" = "0" ]; then
  log "No browser launcher command found on PATH - on macOS, 'open' launches the default browser; on Linux, install one of google-chrome/chromium/firefox."
fi
log "HEADPHONE REQUIREMENT: H2 (the ABX trial) requires real headphones, not speakers - stereo/HRTF separation does not work correctly over room speakers."

section "H1 - Open phase1_room.html"
log "Run this in another terminal, then come back here:"
log "  python3 -m http.server --directory $ROOT/digital_twin 8000"
log "Then open http://localhost:8000/phase1_room.html in a real browser."
pause
ask "Did the page render (room + avatar visible)? (yes/no)"
ask "After clicking Start, did you hear audio appear to come from a direction? (yes/no)"
ask "Did the avatar's glow/mouth visibly change while audio played? (yes/no)"

section "H2 - ABX trial (10 trials, scoring sheet)"
log "Recruit one person NOT briefed on where the avatar is. For each of 10 trials:"
log "  1. Move the mouse to a new spot in the room (changes listener position)."
log "  2. Click Start."
log "  3. Without looking at the screen, have them say which direction the tone"
log "     comes from (left/right/front/back)."
log "  4. Mark correct or incorrect."
log "Gate requires >=8/10 correct."
pause
ask "Enter the score as 'correct/10' (e.g. 8/10):"

section "H3 - A: real proposal from a real owner file"
log "This script does NOT create or read any file under runtime/inbox or runtime/rules."
log "On the personal machine, with real figures, create:"
log "  $ROOT/runtime/inbox/espp_inputs.json"
log "  $ROOT/runtime/rules/uk_tax_rules.json"
log "Then run:"
log "  python3 -B $ROOT/scripts/agents_runner.py --once"
log "Paste the first 10 lines of its output below (or run it yourself and paste):"
pause
if [ "$DRY_RUN" = "0" ]; then
  log "Owner-pasted output (first 10 lines):"
  for i in 1 2 3 4 5 6 7 8 9 10; do
    read -r -p "line $i (blank to stop): " line
    [ -z "$line" ] && break
    log "  $line"
  done
else
  log "[dry-run] (would collect up to 10 pasted lines here)"
fi
ask "What is the fact_id of the resulting proposal (from /console or the output above)?"

section "H4 - C: real decision recorded"
log "In /console, approve or decline the proposal from H3. Then run, using the fact_id"
log "you entered above:"
log "  python3 -B $ROOT/scripts/record_outcome.py --fact-id <N> --outcome accepted|rejected|acted_on|ignored --note \"...\""
log "Then run again:"
log "  python3 -B $ROOT/scripts/agents_runner.py --once"
pause
if [ "$DRY_RUN" = "0" ]; then
  log "Owner-pasted scenario_text (first 5 lines) from the second --once run:"
  for i in 1 2 3 4 5; do
    read -r -p "line $i (blank to stop): " line
    [ -z "$line" ] && break
    log "  $line"
  done
else
  log "[dry-run] (would collect up to 5 pasted lines here)"
fi

section "H5 - cron install (user-level systemd timer, no root)"
log "Install command:"
log "  mkdir -p ~/.config/systemd/user"
log "  cp $ROOT/deploy/user/apex-nightly.service $ROOT/deploy/user/apex-nightly.timer ~/.config/systemd/user/"
log "  systemctl --user daemon-reload"
log "  systemctl --user enable --now apex-nightly.timer"
if [ "$DRY_RUN" = "1" ]; then
  log "[dry-run] NOT executing install commands."
else
  read -r -p "Type 'yes' to run these commands now, anything else to skip: " confirm
  log "owner confirmation: $confirm"
  if [ "$confirm" = "yes" ]; then
    mkdir -p "$HOME/.config/systemd/user"
    cp "$ROOT/deploy/user/apex-nightly.service" "$ROOT/deploy/user/apex-nightly.timer" "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    systemctl --user enable --now apex-nightly.timer
    log "status check:"
    systemctl --user status apex-nightly.timer --no-pager 2>&1 | tee -a "$LOG"
  else
    log "skipped install (owner did not confirm)"
  fi
fi

section "H6 - GitHub Actions: push and open two PRs"
log "On the personal machine, with an authorized remote:"
log "  git remote add origin <your-real-github-remote-url>"
log "  git push -u origin apex/unified-field-integration"
log "Open ONE PR with a deliberately broken isolation test (confirm the workflow FAILS)."
log "Open ONE clean PR (confirm the workflow PASSES)."
pause
ask "Deliberately-failing PR URL:"
ask "Clean PR URL:"

section "Done"
log "Log written to: $LOG"
log "Paste this whole file back into the session."
exit 0
