# Data boundary

Enforced in three places, all checking the same forbidden-path list:
[`.git/hooks/pre-commit`](../scripts/hooks/pre-commit) (local, source of truth
committed at `scripts/hooks/pre-commit` since `.git/hooks/` itself is never
tracked by git), the `data-boundary` job in
[`.github/workflows/apex-gates.yml`](../.github/workflows/apex-gates.yml) (runs
before every other job; no test job runs if it fails), and
[`.gitignore`](../.gitignore) (keeps the paths out of `git status`/`git add -A`
in the first place — a convenience, not an enforcement mechanism on its own,
since `git add -f` bypasses `.gitignore` but not the hook or CI job).

## What is forbidden

```
runtime/inbox/
runtime/rules/
*.sqlite3
*.db
*.db-journal
.env
.env.*
secrets/
user_data/
Owner_Handoff_*.log
biometrics/
```

## Why

This account operates inside an employer-tenant work account, per
`AGENTS.md`'s own standing rule. FINANCE, MEDICAL, biometric and real
user-generated data classes do not enter it — not because the code cannot
technically handle them, but because this repository and its CI history
are visible inside that tenant, and a leaked real financial figure, a real
lab result, or a real biometric file cannot be un-leaked once it is in git
history, even if the file is later deleted.

## What to do instead

Real data stays on the owner's own machine. Code in this repository is the
part that runs the logic; it reaches real data only through an
authenticated API call initiated from the owner's machine, never by this
repository holding the data itself. `scripts/apex_build_order_handoff.sh`
and the owner-local handoff pattern already in this repo follow exactly
this shape.

## How to test the boundary yourself

```bash
bash scripts/test_data_boundary.sh
```

This creates a disposable local clone, installs the committed hook into
it, attempts to commit a fake file at a forbidden path, and asserts the
commit is rejected with the exact `DATA_BOUNDARY_VIOLATION` message and a
non-zero exit code. It cleans up its temp clone whether it passes or
fails.
