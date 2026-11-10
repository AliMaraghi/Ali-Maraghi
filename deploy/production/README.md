# Executable host bundle

Run only through an authenticated host administrator executor, never via self-SSH
or namespace escape. This bundle installs the CURRENT application and worker,
not unimplemented130 integrations/18 roles. No production acceptance claimed.

Validation (no mutation):
python3 -B deploy/production/install.py
systemd-analyze verify deploy/production/apex-worker.service deploy/production/apex-console.service

Host install after actual root-owned /etc/apex/access-origin.json is bound:
python3 -B /home/apexdev/apex-work/deploy/production/install.py --apply --install-dependencies

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

Open deployment gates: production load/rate-limit validation, automatic trusted
JWKS renewal (current snapshot expires within24h and fails closed), host restart
and external founder login/denial/TLS verification. Current standard-library HTTP
origin remains read-only loopback. Do not publish before these gates are accepted.
The bundle is ready for host validation, not a full production-readiness claim.

Rollback only newly installed units: stop/disable apex-console and apex-worker;
retain runtime database and verified deployment-backups. Do not remove existing
units or restore a stale database automatically. Revert only new console DNS/ingress
entries using the captured Cloudflare snapshot, preserving unrelated routes.
