# Owner handoff (2026-11-12) - everything that needs a human, in one place
Prepared by the lead; nothing below has been executed on the host. Status of all new code: TESTS_NOT_RUN until `scripts/pre_activation_check.sh` is run.

## 1. One privileged command (sudo password once, then one e-mail prompt)
Verifies the SHA-256 of the three root-run files, then runs `scripts/owner_handoff.sh prepare`, which: validates the reviewed bundle; reads the Cloudflare Access team + application AUD (public identifiers) from the live
console redirect; asks for the Access owner e-mail; creates `/etc/apex`; runs the reviewed `install.py --bind-access` (writes `/etc/apex/access-origin.json`); writes `/etc/apex/approvals-runtime.json`
(random secret, apexdev:apexdev 0600, never displayed, never overwritten if present); replaces the temporary session-run legal-pages server with a managed `apex-legal.service`; runs `loginctl enable-linger apexdev`.
It stops instead of overwriting anything that differs. It does not touch DNS, tunnel routes, other services, or secrets for Google/Meta (those stay in the `activate` phase, typed hidden).

## 2. Pre-activation check (no sudo): `scripts/pre_activation_check.sh`
Compile every .py; full offline test suite; deployment bundle tests; installer validation (no mutation); `systemd-analyze verify`; dev approvals config check; two public GETs of /privacy and /terms. Writes `runtime/dev/pre_activation_report.json`.

## 3. Activation (after the check passes): `sudo bash scripts/owner_handoff.sh activate`
Runs the reviewed `install.py --apply --install-dependencies` (apt python3-waitress; runs the test suite as its own gate; online SQLite backup; installs and starts apex-console and apex-worker) and then optionally
the reviewed provisioning scripts for Google and Meta (hidden secret prompts + typing REVIEWED to attest the privacy review).

## 4. Human logins that cannot be automated
Google (reset the client secret first: it was pasted in chat on 2026-11-12), Meta app secret, and the two consent clicks. Banks: no live route is available (see CAPABILITY_MATRIX.json).
