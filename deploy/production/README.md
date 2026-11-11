# Executable host bundle

Run only through an authenticated host administrator executor, never via self-SSH
or namespace escape. This bundle installs the CURRENT application and worker,
not unimplemented130 integrations/18 roles. No production acceptance claimed.

Validation (no mutation):
python3 -B deploy/production/install.py
systemd-analyze verify deploy/production/apex-worker.service deploy/production/apex-console.service

Bind Access once (public identifiers only; root; installs hash-pinned root-owned
refresher copy at /usr/local/lib/apex and writes /etc/apex/access-origin.json):
sudo python3 -I -B /home/apexdev/apex-work/deploy/production/install.py --bind-access --team TEAM --aud AUD --owner OWNER_EMAIL
--apply then enables apex-access-jwks.timer (hourly key renewal; 12h snapshot).

Host install after actual root-owned /etc/apex/access-origin.json is bound:
python3 -I -B /home/apexdev/apex-work/deploy/production/install.py --apply --install-dependencies

The installer refuses non-root/isolated PID1, changed original manifesto,
conflicting existing units, runtime symlinks and invalid Access configuration.
It verifies dependencies and tests, takes a SQLite online backup and integrity
check, installs identical-repeat-safe units, enables startup, starts services and
checks active status. Existing database is retained; no DB migration required.
It never changes cloudflared, DNS, private credentials or other services.
Dependencies use Ubuntu repositories; no external paid services. Tests may report
optional web skips; these are not production acceptance. Failed commands stop the
installer. New identical units can be retried without overwriting existing changes.

Cloudflare preparation:
python3 -B deploy/production/cloudflare_plan.py --account ACTUAL_ACCOUNT_ID --zone ACTUAL_ZONE_ID --tunnel ACTUAL_TUNNEL_UUID --owner ACTUAL_OWNER_EMAIL

This emits payloads and ordered preconditions, not a fabricated live API result.
Read current remote state and merge existing ingress before applying. Do not create
a new tunnel or overwrite existing policy. API/auth/hooks stay unpublished.
Both dashboard pages use the single console origin. Access config field schema is
in docs/apex_status/ACCESS_ORIGIN_REPORT.md. No test keys or placeholder identity.

Open deployment gates: production load/rate-limit validation, host restart
and external founder login/denial/TLS verification. The production origin uses Waitress behind loopback with application Access validation. Do not publish before these gates are accepted.
The bundle is ready for host validation, not a full production-readiness claim.

Rollback only newly installed units: stop/disable apex-console and apex-worker;
retain runtime database and verified deployment-backups. Do not remove existing
units or restore a stale database automatically. Revert only new console DNS/ingress
entries using the captured Cloudflare snapshot, preserving unrelated routes.

## Release safety corrections
Root apply requires Python isolated mode (-I), sanitized child process environment,
and reviewed SHA256-pinned unit contents captured before unprivileged tests run.
Changing units requires intentional pin updates. Unit creation is atomic without
overwriting concurrent host administrator changes; identical reinstall is a no-op.
Online SQLite backup runs as apexdev, never as root in a user-writable directory.
An older root-owned deployment-backups directory may require explicit ownership
repair after review; installer fails rather than changing it silently.

Production console now targets apex.console_server (Waitress), installed through
Ubuntu python3-waitress when --install-dependencies is explicitly used. Actual
host package version/security acceptance remains unverified until installation.
No live tests, config writes or service changes occurred during bundle validation.
A package-install/test/start failure stops apply; automatically rolling back a
preexisting service is deliberately not attempted. Deployment receipt only proves
active units, never public HTTPS or founder login.

Cloudflare owner policy review can consume the complete authenticated app policy
snapshot via cloudflare_plan.py --existing-policies PATH. It rejects broad Everyone,
alternate-owner allow policies and bypass/non-identity decisions, including when
a correct owner policy also exists. Snapshot validation does not prove its live
origin or pagination completeness. Fetch all app policy pages using the approved
management connection before relying on it; owner login remains a separate gate.

## Optional integrated Google owner routes
The console automatically enables `/connections/google` and the fixed
`/auth/google/start`, `/auth/google/callback`, `/auth/google/disconnect`,
`/auth/logout`, `/connections/google/sync` routes only when the protected file
`/etc/apex/google-runtime.json` exists. Without it, the connection page reports
BLOCKED_EXTERNAL_AUTH. No Google secret or encryption key is generated.

Provision this file through the authenticated host secret-management path,
readable only by the console service identity (mode0600). Required JSON fields:
`owner` (must match Access owner), `client_id`, `client_secret`,
`redirect_uri` (exact https://console.apexcorelab.uk/auth/google/callback),
`encryption_key` (existing persistent Fernet key), `review_reference`,
`retention_days`, `mixed_content_reviewed` (explicit booleantrue).

Recurring Gmail sync uses the same scheduler/worker and Ledger, not a new
service. The owner arms it at `/connections/google/schedule` (15-minute
interval, 672 runs, then re-arm) and disarms at `/connections/google/unschedule`.
The worker executes armed runs only with `--google-config`, supplied by the
opt-in drop-in `apex-worker.service.d/google-sync.conf.example`, which also
widens `RestrictAddressFamilies` to AF_INET/AF_INET6. Three consecutive failures
or RESYNC_REQUIRED disable the schedule; a run never starts consent.
Never put actual values in Git or chat. Retention policy is an import gate;
automatic deletion/expiry of synchronized content is not implemented.

Access JWT authentication still runs before every route. Owner session is bound
to that verified token, expires after15minutes, and uses a Secure/HttpOnly/Lax
host-only cookie. POSTs require exact Origin and form CSRF. A changed Access token
requires a new application session; callbacks then require restarting consent.
The origin must receive Host console.apexcorelab.uk. Callback is a top-level GET;
Access/session must remain valid. No separate unauthenticated callback is enabled.
Verify actual Cloudflare cookie/redirect behavior before publication.

The console now needs write access only to the existing runtime directory for
sessions, encrypted credentials and sync. The pinned unit permits that directory.
Installer collision checks still reject changing already-installed differing units;
use an authenticated reviewed unit upgrade, never overwrite around this guard.
Google sync is an explicit bounded owner POST, not recurring worker scheduling.
Logout ends the local app session only; it does not terminate Cloudflare identity.
Local Google disconnect does not revoke the remote grant. No API/hook publication.
