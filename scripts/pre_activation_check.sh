#!/usr/bin/env bash
# Pre-activation check. Runs as the normal user (no sudo). Read-only apart from its own temporary test folders and one report file.
# Touches: repository files (read), temporary directories created and removed by the tests, runtime/dev/pre_activation_report.json (write),
# and two public GET requests to https://apexcorelab.uk/privacy and /terms. It changes no service, no config, no DNS, and deletes nothing of yours.
set -uo pipefail
cd /home/apexdev/apex-work
export PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8
mkdir -p -m 700 runtime/dev
REPORT=runtime/dev/pre_activation_report.json
FAILS=0
RESULTS=()
step() {   # step <name> <command...>
  local name="$1"; shift
  local out status
  out="$("$@" 2>&1)"; status=$?
  [ $status -eq 0 ] || FAILS=$((FAILS + 1))
  printf '%-34s %s\n' "$name" "$([ $status -eq 0 ] && echo PASS || echo "FAIL (exit $status)")"
  [ $status -eq 0 ] || printf '%s\n' "$out" | tail -n 15 | sed 's/^/    /'
  RESULTS+=("$(NAME="$name" STATUS="$status" OUT="$(printf '%s' "$out" | tail -n 3)" python3 -I -c 'import json,os;print(json.dumps({"step":os.environ["NAME"],"exit":int(os.environ["STATUS"]),"tail":os.environ["OUT"]}))')")
}
compile_all() {
  python3 -B - <<'PY'
import os, sys
bad = 0
for base in ("core", "scripts", "deploy", "tests"):
    for root, _, files in os.walk(base):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    with open(path, encoding="utf-8") as stream:
                        compile(stream.read(), path, "exec")        # syntax check only: writes no bytecode, executes nothing
                except SyntaxError as exc:
                    bad += 1
                    print(f"{path}:{exc.lineno}: {exc.msg}")
sys.exit(1 if bad else 0)
PY
}
step "1 compile every .py"            compile_all
step "2 full offline test suite"      python3 -B scripts/test_offline.py
step "3 deployment bundle tests"      bash -c 'cd deploy/production && python3 -B -m unittest test_bundle -q'
step "4 installer validation"         bash -c 'python3 -B deploy/production/install.py | grep -q BUNDLE_CHECKED_NOT_DEPLOYED'
step "5 systemd unit verification"    systemd-analyze verify deploy/production/apex-worker.service deploy/production/apex-console.service deploy/legal/apex-legal.service deploy/production/apex-bridge.service deploy/production/apex-agents.service
step "6 dev approvals config check"   python3 -B scripts/dev_approvals_config.py check --owner dev-owner@example.test
step "7 public legal pages (GET)"     deploy/legal/check_legal_pages.sh
python3 -I -c 'import json,sys;print(json.dumps({"generated_by":"scripts/pre_activation_check.sh","failures":int(sys.argv[1]),"steps":[json.loads(x) for x in sys.argv[2:]]},indent=1))' "$FAILS" "${RESULTS[@]}" > "$REPORT"
echo; echo "report: $REPORT   failures: $FAILS"
exit $([ "$FAILS" -eq 0 ] && echo 0 || echo 1)
