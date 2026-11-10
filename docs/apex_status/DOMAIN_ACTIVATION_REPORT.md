# apexcorelab.uk activation attempt — 10 November 2026

Entry b2f7b44, branch apex/unified-field-integration. No Cloudflare or production mutation performed. No working APEX public URLs yet.

Observed DNS: both alina.ns.cloudflare.com and skip.ns.cloudflare.com answer authoritatively for apexcorelab.uk. Each returned NXDOMAIN for console, api, auth and hooks. Exact queries/UTC times are in reports/validation/domain_dns.json. This proves authoritative service, not Cloudflare API zone status=active or an active Universal certificate pack. Those two states remain UNVERIFIED.

No Cloudflare connector or authenticated browser tool is available in this session. Presence-only checks found no CLOUDFLARE_API_TOKEN, CF_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_ZONE_ID or TUNNEL_TOKEN; no ~/.cloudflared directory. This does not prove the owner's account lacks tunnels. Browser login elsewhere is not an API credential. No browser cookies/private secrets scanned.

cloudflared is absent from PATH; system cloudflared reports inactive. Docker service is active but docker ps was denied access to its socket. No privilege escalation attempted. Existing deployment topology and container upstreams therefore remain unverified. Existing repo API lacks application authorization; local owner-view is ten-minute development-only; OAuth callback and signed webhook services are absent. Routing any of these publicly would violate the activation prerequisites.

Local changes: deploy/cloudflare/activation.json keeps all four hosts disabled; remote-deny-all.json provides only http_status:404; check_domain_activation.py rejects enabled routes, database/admin passthrough and unknown hostnames. A systemd example uses DynamicUser and LoadCredential/token-file, never a token on the command line. It is a template, not installed or runtime-validated; binary location and credentials file require provisioning.

## Exact minimum access needed

For read-only account reconciliation, securely bind a scoped Cloudflare API token (not pasted into chat) with Zone Read, DNS Read and SSL and Certificates Read restricted to apexcorelab.uk; Account Cloudflare Tunnel Read and Access: Apps and Policies Read restricted to the owning account. Supply account/zone identifiers through approved configuration or discover them via the scoped API. No Global API Key required.

For the requested changes after upstream gates pass: Account Cloudflare Tunnel Edit (API permission Cloudflare Tunnel Write or equivalent scoped cloudflared connector permission), Zone DNS Edit limited to apexcorelab.uk, and Access: Apps and Policies Edit for the account. No billing, certificate purchase, registrar or unrelated-zone permissions needed. The runtime requires only the selected tunnel token, stored separately from the management token.

Owner identity/IdP subject must be verified before an Access allow policy is created; do not infer the owner from a domain suffix. Need an approved VPS administration path to inspect origins and install a narrowly scoped cloudflared service; current Docker socket access is denied. Existing user order authorizes this integration, but does not grant missing OS/API capabilities.

## Activation and rollback gates

Reuse a suitable remotely managed tunnel after authenticated inventory; otherwise create apex-production with config_src=cloudflare. Start with deny-all ingress. Verify Universal certificate status via certificate packs API; do not order paid certificates. Create owner-only Access applications for console/admin API before DNS/ingress exposure and retain application authorization. OAuth callbacks must have their own noninteractive route with application state/nonce/PKCE/redirect/token validation. Webhooks require signature/time/replay checks. Keep auth/hooks absent until those services exist and pass tests. Never route PostgreSQL/Redis/n8n administration.

No activation is inferred from a boolean in the local manifest. Capture upstream and unauthorized-request tests, HTTPS/Access tests, tunnel restart/health evidence and exact prior Cloudflare config before activation. Rollback removes only newly created records/routes/applications and restores captured prior config; never delete a pre-existing tunnel or volume. No rollback needed for external resources in this run because none changed.

Official references reviewed:
- https://developers.cloudflare.com/tunnel/get-started/
- https://developers.cloudflare.com/tunnel/reference/run-parameters/ (token-file requires2025.4.0+)
- https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/list/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/

Next local command: python3 -B scripts/check_domain_activation.py. Next external step requires the scoped API binding and VPS inspection capability above. Paid spendGBP0; no public routes, service installation or purchases.
