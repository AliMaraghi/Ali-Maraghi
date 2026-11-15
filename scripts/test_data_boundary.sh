#!/usr/bin/env bash
# Gate P1: proves .git/hooks/pre-commit rejects a forbidden real-data path.
# See docs/DATA_BOUNDARY.md. Creates a temp clone, attempts a violating
# commit, asserts rejection, cleans up. Exits 0 only if the rejection
# behaved exactly as specified.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_CLONE="$(mktemp -d)"
trap 'rm -rf "$TMP_CLONE"' EXIT

git clone -q "$REPO_ROOT" "$TMP_CLONE"
cp "$REPO_ROOT/scripts/hooks/pre-commit" "$TMP_CLONE/.git/hooks/pre-commit"
chmod +x "$TMP_CLONE/.git/hooks/pre-commit"

cd "$TMP_CLONE"
git config user.email "data-boundary-test@local"
git config user.name "data-boundary-test"
mkdir -p runtime/inbox
echo '{"fake": "real-shaped data, never actually real"}' > runtime/inbox/test.json
git add -f runtime/inbox/test.json   # -f: bypass .gitignore itself to prove the HOOK (not .gitignore) is what blocks this

set +e
commit_output="$(git commit -m "attempted data-boundary violation (synthetic test)" 2>&1)"
commit_exit=$?
set -e

echo "$commit_output"

if [ "$commit_exit" -eq 0 ]; then
  echo "FAIL: commit was NOT rejected (exit 0) - data boundary is not enforced"
  exit 1
fi

if ! echo "$commit_output" | grep -q "DATA_BOUNDARY_VIOLATION: runtime/inbox/test.json"; then
  echo "FAIL: commit was rejected, but not with the expected DATA_BOUNDARY_VIOLATION message"
  exit 1
fi

echo "PASS: commit rejected, exit=$commit_exit, message matched"
exit 0
