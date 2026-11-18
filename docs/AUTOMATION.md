# What runs by itself, and where it stops (2026-11-18)

| Loop | What it does unattended | Where a person is required |
|---|---|---|
| `apex-autoupdate` (root, every 10 min) | Pulls GitHub fast-forward, rebuilds, restarts, health-checks, rolls back | Nothing, once a commit is on GitHub |
| `apex-autopush` (root, every 15 min) | Scans unpublished server commits for keys/account numbers/passwords, then pushes | Only if the scan finds something |
| `apex-evolution-apply` (apexdev, every 15 min) | Applies an evolution proposal the owner APPROVED: re-checks hash, guard and score, runs tests, commits; reverts on failure | Approval in the console |
| `scripts/run_evolution.py` (no timer) | Tries seeded weight mutations in the sandbox, raises at most one proposal | `ENABLE_EVOLUTION_SANDBOX=true`; approval |
| `scripts/run_content.py` (no timer) | One post draft in the owner's voice through the critic, queued as a proposal | `ENABLE_AUTONOMOUS_SOCIAL=true`; topics file; approval; owner posts |
| Gmail (`gmail_sync.py`, `gmail_drafts.py`) | Read-only sync and draft-only creation already exist | Google OAuth consent by the owner - not yet connected |

Not built, by decision: self-written code changes outside the EVOLVE-BLOCK, auto-merge without approval,
randomised delays or fingerprint changes meant to avoid platform bot detection, any send/post connector.
The two root scripts live in /usr/local/sbin, outside the repository, so a pushed commit cannot change them.
