# APEX Intelligence Core — public legal pages

Prepared 12 November 2026 for the existing APEX infrastructure. Two standalone, dependency-free HTML pages:

- `privacy/index.html` → desired public URL: `https://apexcorelab.uk/privacy`
- `terms/index.html` → desired public URL: `https://apexcorelab.uk/terms`

## Critical deployment preconditions

1. This archive is **NOT deployed** to IONOS or Cloudflare. Do not claim the URLs work merely because the files exist.
2. On existing VPS `31.70.173.143`, inspect the current proxy, web root, Cloudflare Tunnel/DNS and Access rules. Preserve all existing configs and databases.
3. Serve `/privacy` and `/terms` as **public HTTPS routes**, while leaving the protected APEX console behind its existing Cloudflare Access policy. Prefer the root apexcorelab.uk hostname rather than exposing all console routes.
4. Copy the matching `privacy/` and `terms/` directories to the already-approved document root and configure path rewrites as needed. Avoid replacing existing virtual hosts or creating infrastructure.
5. Verify each route returns HTTP 200 and actual HTML publicly via a fresh unauthenticated browser, with valid TLS and no redirect loop.
6. Ensure the data-protection contact email entered into Enable Banking is active and reachable. This version refers users to that registered email instead of publishing a private email address.
7. **Before handling live bank data**, verify the policy's assertions against actual security controls, retention/deletion behavior and recipients; revise any conditional descriptions accordingly.

The application description and consent disclosures must reflect actual implementation. Restricted Enable Banking linked-account activation does not require provider validation of URLs, but registered Production fields still include both URLs and data-protection email.

No third-party scripts, analytics, fonts, or trackers are included in the static HTML.
