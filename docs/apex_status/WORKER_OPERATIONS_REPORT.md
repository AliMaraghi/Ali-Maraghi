# Worker operational observations and bounded failure

Entry b8390d0; checkpoint ad6bd94 was historical, not current. Branch preserved.
Actual host interface ens6 has31.70.173.143. SSH agent lookup failed with
"No such file or directory". No new sudo attempt, self-SSH sandbox escape or
production mutation was attempted. Available plugin search Cloudflare/SSH/IONOS
returned no results; this is not an exhaustive statement about all integrations.

Implemented worker_health in the existing SQLite journal: one current observation
plus atomic append-only audit receipts. Dashboard reads actual state, observation
age, freshness and redacted error type. Clock rollback fails freshness. A recent
heartbeat is not proof of VPS deployment, successful missions or laptop independence.
Clean shutdown records EXITED; abrupt termination leaves a stale observation.

Foreground worker now exits78 after three consecutive cycle exceptions, stricter
than three repeats of one failure signature. A successful cycle resets the counter.
Database/audit-write failure exits immediately; it does not fake a health receipt.
The existing service template adds RestartPreventExitStatus=78, preventing an
automatic restart loop after exhaustion. Template not installed or systemd-tested.
Other crashes retain existing bounded supervisor restart settings. Recovery after
exhaustion requires diagnosis and an explicit supervisor start; no credentials or
policy are reset. Blocked individual missions still permit independent missions.

212 tests run:210 passed,2 optional web dependency skips,zero failures/errors.
New tests cover absent/fresh/stale/backwards-clock observations, audit rollback,
three-failure shutdown/redaction and clean exit. Existing security/recovery tests
remain. No independent performance advantage or production acceptance inferred.

Rollback: revert code/template; leave additive worker_health table and historical
receipts intact. No existing mission ledger was changed by isolated tests.
No live provider test, new field trace, income, deployment or API spend in this
increment. Full130-provider/18-role target remains incomplete, with substantial
independent engineering still outstanding. Authorization is not the missing item:
a usable execution path and actual credential binding are required for deployment.
