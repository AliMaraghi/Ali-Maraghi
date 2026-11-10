# Security and 24/7 reliability gates — fail-closed

**This ZIP is a development reference, NOT production hardening.** The founder's own private IONOS VPS is already running a small bootstrap. The code in this ZIP is unrelated to the running service unless deliberately integrated/tested by Codex, and no deployment authority is granted.

## Threat model

1. **Injection:** third-party sources attempt to alter instructions, call privileged tools or exfiltrate credentials. Control: never compile external text into system prompts, parse as data, policy gateway and tool sandbox, no secret tokens visible to data agents.
2. **SSRF and redirects:** a malicious URL resolves to localhost, metadata services or internal address, or redirects to one. Our offline URL parser blocks IP literals and local hostnames but **does not** resolve DNS or follow redirects; production fetchers must validate EVERY resolved address and redirect in the network layer, use allowlisted hosts and direct egress firewall.
3. **Secrets:** `.env`, SSH keys, cloud credentials and corporate material accidentally copied to code, logs or public repos. Controls: denylist and secret scanner, dedicated Vault/KMS, minimum scopes, least privilege and incident key rotation.
4. **Cross-domain leaks:** medical, legal, benefits, social and private intimacy data flow to publishing agents. Controls: domain-boundary access checks, consent/declassification, redacted derived signals and purpose limitation.
5. **Model escalation:** a language model tries to change its own permissions, approve its own spend, or write a different connector. Control: deterministic gateway independent of model, ability manifest, one-time human approvals, idempotency, network and file sandbox.
6. **Test cheating:** developer/Codex seeds fixtures, leaks held-outs, modifies baseline, scores itself or optimises synthetic cases. Control: signed test artifacts, independent reproduction, blinded cases, pinned baselines, exact version/seed and no auto-promotion.
7. **Outages and cost runaway:** VPS crash, dependency upgrade, Redis memory exhaustion, infinite retry, insufficient disk, DB corruption, LLM runaway tokens. Control: bounded jobs, health and functional canaries, budget reservation, backups and rollback.
8. **Information deception:** user sees 'healthy' even when monitor has zero usable sources or engine has no authorisations. Control: contract-specific functional tests and visibly separate live/synthetic/unverified statuses.

## Hard stage gates

- G0: canonical original manifest SHA matches and acceptance A01–A09 present.
- G1: all 19 numbered chapters mapped to module/test/gap records; none silently deleted.
- G2: adversarial injection/SSRF, permission, consent, budget and data-boundary negative tests.
- G3: reproducible environment and dependencies: build, unit, integration, restore, load and real external connector test; skipped integration tests are open debt.
- G4: actual user-value domain test: real opportunity verified or original film rendered and human-evaluated or personally authorised workflow delivered.
- G5: repeated backup/restore drill, measured MTTR, tested 4-phase kill switch, app lockscreen preview and TLS authentication.
- G6: staged release + explicit owner approval + rollback evidence; no 'deployment-ready' labels from tests alone.

## Kill switch four stages (original §0-4)

1. `FREEZE_INGRESS`: stop accepting new tasks, keep durable queue for recovery.
2. `DISABLE_EGRESS`: deny writes to external world (email, publish, payment, external account mutation).
3. `STOP_EXECUTION`: graceful stop of workers after durable state is recorded.
4. `REVOKE_CREDENTIALS`: separately managed authority withdraws tokens; irreversible/costly and requires recovery workflow.

The offline prototype records a control state but does not control deployed Docker, credentials or n8n. Never claim the actual kill switch works before testing the production connectors. Recovery should require explicit founder approval and drill evidence.

## Access architecture and iPhone interface

- Do not expose port 8080 or PostgreSQL, Redis or n8n publicly by merely changing Docker bind addresses.
- Use private tailnet/VPN or equivalent + TLS + legitimate per-device authentication and rate limiting.
- Dashboard: read-only status/report feed, approvals with clear action details and expiry, kill stages, tasks and budgets, sources/claims, evaluation outcomes, rollback and incidents. No shadow access to corporate or medical context.
- iPhone control requires an ACTUAL implemented UI and tested network path. A PWA design or screenshot alone is not delivery.

## Backup and restore

A tarball of code without `.env` is only code backup, NOT recoverability of PostgreSQL/Redis or production state. Need encrypted offsite backups including DB snapshots, verified checksums, retention, staged restore and restoration test evidence. Never put keys in the same storage bucket as ciphertext.

## Remaining P0 findings

The current reference uses SQLite (not encrypted), one local database connection, a hash-linked log (tamper-evident but not protected against a privileged attacker who rewrites every digest), and a simplified offline work queue. It does not provide production concurrency, user identity provider, secure secrets store, live broker, n8n, real API adapters, operational metrics or 24/7 service. These are explicit blockers, not 'done' work.
