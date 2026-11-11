# Command Centre implementation evidence

Current implementation extends existing dashboard, journal and CLI; no restart or
replacement stack.12 actual sections: overview, system map,18 source role slots,
connectivity, missions, opportunities, finance, research, security, timeline,
decisions and reports. Responsive navigation, light/dark, Persian/English shell,
RTL, technical disclosures, searchable event timeline and authenticated JSON export.
Source records remain in their source language. No invented130-provider inventory.
Metrics identify provenance, observed time and limitations. No revenue is inferred.

Production origin: apex.console_server WSGI via Waitress; loopback-only,4threads,
32connections, bounded requests and global300/min rate cap. Access JWT required
for every route including assets; no Basic fallback, private payload projection,
external JS, telemetry or remote calls. CSP restricts script/style/connect to self.
Public routes are not activated. Read-only web surface; STOP remains the existing
operator CLI, clearly unavailable as a web action. Same API data at /api/status.
The shared global rate cap can impair owner availability under hostile origin
traffic; upstream Access is required. No general load/penetration certification.

Verified actual Waitress+Chromium against existing79-event journal, ephemeral
synthetic RSA owner identity:401 for anonymous console/reports/API/assets,200 for
authenticated views,12 navigation sections,18role slots,390px no horizontal overflow,
RTL/theme changes and desktop rendering without JS errors. Not actual Safari,
public Cloudflare login, live deployment or reboot acceptance. Screenshots and
receipts under reports/validation/console_*. Test harness shuts down its server.
Local dependencies only in ignored work/:Waitress3.0.2,Playwright1.65.0; Ubuntu
browser libraries extracted there, no system package installation. Official server
settings checked against https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html
Host package version must be verified during approved installation.

Independent release review corrected root installer: reviewed captured unit hashes,
python -I requirement, sanitized subprocess environment, unprivileged SQLite backup,
non-overwriting atomic unit publication. Cloudflare policy snapshot validation rejects
non-owner allows and bypass. It is not proof of current account policy. JWKS config
reload is fail-closed; automatic trusted renewal remains open.11 bundle tests and
systemd syntax validation pass.233 regression tests:231passed,2optional web skips.
Initial run encountered124 filesystem errors after sandbox reset; permission was
restored and tests rerun. No tests weakened or skipped to hide those errors.

Original manifesto hash unchanged. Existing mission/source records untouched.
No paid API calls, production mutations, new live provider probes or income.
Historical3 providers have live exchange evidence;0 fully accepted agents,
1 deterministic role handler. The mandatory product acceptance is BLOCKED.

Missing access unchanged: authenticated host administrator executor/PolicyKit
session and rotated scoped Cloudflare management binding plus actual owner app
configuration. No repeated infrastructure diagnosis, self-SSH or namespace escape.
Next host operation after secure binding: python3 -I -B
/home/apexdev/apex-work/deploy/production/install.py --apply --install-dependencies
Follow bundled rollback instructions; retain ledger and deployment backups. Public
DNS publication must wait for actual owner-policy, origin and HTTPS acceptance.
