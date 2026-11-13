# BUILD_STATE (2026-11-12)

Source brief: owner-supplied BUILD_PROMPT / API_HINTS (pasted in session, not stored as a file).
The supplied `apex-builder` setup script was reviewed and **not run**: this session already
has file and test tools, and a stdio MCP bridge created on the VPS would not be reachable
from Claude Desktop on the owner's own computer.

## Completed this increment
- `core/apex/kernel/approvals.py`: approval state machine on the hash-chained Ledger.
  Payload-hash-bound HMAC single-use token, identity binding, no agent/self approval, replay and
  tamper rejection (audited in own transactions), 24 h unanswered-proposal expiry (separate from the
  15 min approval-confirmation validity), durable-stop re-check at execution, mock-only execution.
  Daily limit: 3 admitted routine requests per UTC day, counted whatever their outcome (deny-and-
  repropose cannot bypass); overflow is DEFERRED and `release_deferred` makes still-valid ones
  reviewable the next day, never approving. Model commentary stored apart from the hashed payload.
- `core/apex/approvals_web.py` + `console_server.py` wiring: GET /approvals, GET /approvals/<id>
  (trusted facts, exact parameters, evidence, deadline, hash; model commentary in a separate
  labelled untrusted box; everything HTML-escaped); POST approve/deny/execute need Access-bound owner
  session, same-origin form, exact fields, session CSRF and the payload hash that was displayed.
  Viewing never mutates a proposal. CSP form-action 'self' only on these pages.
  Config: `/etc/apex/approvals-runtime.json` (template: deploy/production/approvals-runtime.example.json).
  Unconfigured -> 503 BLOCKED_EXTERNAL_AUTH. `google_web.owner_session` may open a session on GET /approvals*.
- `scripts/demo_approval_flow.py`: synthetic end-to-end demo through the real ConsoleApp (mock action).
- `core/apex/kernel/budget.py`: effective-dated `cost_registry` (integer 1/1000-pence prices, source,
  verified_at), per-pool (core/intelligence/studio/retry) and `global` caps by day/week/month, atomic
  reservation (single write transaction), ceiling-to-pence, unknown/not-yet-effective/stale (>30 d)
  price blocks, zero paid budget by default (registered zero-price mock SKUs only), idempotent keys,
  retries only from the retry pool naming the original key, settle/release with overrun recorded.
  Tested incl. 12 concurrent writers against a 50p cap -> exactly 4 succeed.
- Earlier: `agent_contract.py` (5c48de6), `deploy/legal/`.

## Commands actually run this session and results
- `PYTHONPATH=core:tests python3 -B -m unittest tests.test_approvals_web tests.test_approvals`: 26 tests OK.
- `scripts/demo_approval_flow.py`: propose PENDING, view 200 no state change, bad CSRF 403, approve 303,
  replay 403, mock execute 303, audit chain [proposed, approved, executed].
- `PYTHONPATH=core:tests python3 -B -m unittest tests.test_budget`: 10 tests OK.
- `scripts/test_offline.py` (final, this increment): 357 run, 355 passed, 2 skipped (optional web deps), 0 failures, 0 errors.

## Live / deployment status (separate from code)
- Public legal pages: verified HTTP 200 at https://apexcorelab.uk/privacy and /terms on 2026-11-12.
  Served by a session process; persistence needs `sudo loginctl enable-linger apexdev` (owner).
- Google OAuth client and Meta app created by owner; nothing connected; console callback
  service is not running persistently.
- Bank aggregation: GoCardless Bank Account Data signups disabled; Yapily requires business
  licensing. No personal automatic route confirmed for Santander/HSBC/Halifax/Lloyds/NatWest.
  Existing CSV statement parser (`finance.parse_statement`, generic format) verified offline.

## Sudo blocker scope (resolved 2026-11-12)
`approvals-runtime.json` is application-owned configuration, not administrator security policy:
`protected_json` accepts a regular file mode 0600 owned by root or the service user, and the console
already takes `--approvals-config`. `/etc/apex/...` stays the production DEFAULT (unchanged, asserted by a test).
- Development-only path: `scripts/dev_approvals_config.py generate|check` writes
  `runtime/dev/approvals-runtime.dev.json` (Git-ignored, 0600, O_EXCL, never prints the secret, refuses any
  path outside `runtime/`, so never /etc). `check` uses the production loader (owner match, mode, >=32-char secret).
  Generated and checked locally; tests/test_dev_config.py (5 tests).
- Production installation of /etc/apex/approvals-runtime.json: PENDING (owner/admin; needs sudo).
  Template: deploy/production/approvals-runtime.example.json; owner 0600, apexdev or root, `owner` must equal the Access owner.
- Not startable here: `waitress` is not installed (`ModuleNotFoundError`), so the real listener was not started;
  ConsoleApp is exercised through WSGI in tests instead.

## Capability matrix
`docs/apex_status/CAPABILITY_MATRIX.json` (16 services across finance, email, messaging, social, dating,
infrastructure, health, location, media). `tests/test_capability_matrix.py` checks every listed file exists,
all nine domains are present, every entry has a blocker/next action, and none claims a verified live link.

## Action Gateway (new)
`core/apex/kernel/gateway.py`: typed exact-field payloads per action kind; submit -> approval -> execute re-checks
kill state, durable stop, domain, sensitivity and adapter configuration; atomic budget reservation before dispatch,
settle on success, release on failure, retries only from the retry pool; unconfigured adapter -> NOT_CONFIGURED
(no simulated success); all steps audited. Only local-record and mock adapters exist; no external adapter is registered.
tests/test_gateway.py (8 tests).

## Monzo adapter (new)
`core/apex/monzo.py`: read-only accounts/balance/transactions with strict parameter validation, injectable transport
(live transport pinned to api.monzo.com, never run), NOT_CONFIGURED without a token, non-leaking errors, pagination by
transaction id (bounded 50 pages, de-duplicated), normalisation to the finance ledger's transaction shape, and the
5-minute full-history rule exposed as `coverage()`. Endpoints verified from docs.monzo.com on 2026-11-12.
tests/test_monzo.py: 8 tests. Starling NOT implemented: its docs page returned only a title when fetched.

## Runnable DEVELOPMENT console (2026-11-12) - not a production deployment
- Interface: WSGI (`apex.console_server.ConsoleApp`, served with Waitress). Dependency: `waitress==3.0.2`, pinned with the
  PyPI-published SHA-256 in `requirements-console.lock` (trust-on-first-use). This server has NO pip/ensurepip/uv/virtualenv,
  so nothing was installed with pip: `scripts/fetch_locked_wheels.py` downloads the pure-Python wheel, checks the hash and unpacks
  it into the Git-ignored project folder `.devdeps/`. Production still uses the Ubuntu `python3-waitress` package via the reviewed installer.
- Private dev config (all under Git-ignored `runtime/dev/`, 0600): `approvals-runtime.dev.json`, plus a LOCAL development Access snapshot
  `access-origin.dev.json` signed by a throw-away key `access-dev-private.pem` (issuer `https://apex-dev.cloudflareaccess.com`,
  valid 24 h, not a Cloudflare configuration; rerun `prepare` to renew). Helper: `scripts/dev_console.py prepare|run|token`.
- Start command (run 2026-11-12): `setsid nohup env PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/dev_console.py run --port 18765`
  (log `runtime/dev/console.log`, pid in `runtime/dev/console.pid`).
- Actual status: listening on 127.0.0.1:18765 only (`ss`: LISTEN 127.0.0.1:18765), PID 1171769. Manual requests: no token -> 401;
  dev token -> 200 for /status.json, /console, /approvals; garbage token -> 401. Not exposed through the Cloudflare tunnel.
  Stop with `kill $(cat runtime/dev/console.pid)`. The process does not survive a reboot (no service, no linger).
- Caveat: ConsoleApp uses one root for evidence documents and the journal, so this listener reads and writes the project's local,
  Git-ignored `runtime/kernel.sqlite3` (owner-session rows; `proposals`/approval tables were created there by the first `/approvals` request).
  An earlier attempt with an isolated journal gave 503 EVIDENCE_UNAVAILABLE because the dashboard needs docs/ and .git under its root;
  an empty folder `runtime/dev/workspace/` from that attempt is unused.
- Status of changed implementation: TESTS_NOT_RUN (py_compile and the manual requests above only).

## Starling, Gmail drafts and adapter bindings (2026-11-12) - TESTS_NOT_RUN
- Worker C (isolated copy, lead-reviewed, copied unchanged): `core/apex/starling.py` - GET-only accounts, balance, incremental feed
  (`changesSince`, cursor lags newest `updatedAt` by 300 s), upsert by `<accountUid>/<feedItemUid>`, integer minorUnits + currency preserved,
  `redact()`, private token file reader, `READ_ONLY_OPERATIONS` allow-list. Sources: official SDK files and test fixtures; unconfirmed:
  direction IN, statuses other than PENDING/SETTLED, paging, rate limits (`docs/apex_status/integrations/starling.md`, handoff `worker_c.md`).
- Lead: `core/apex/gmail_drafts.py` (draft creation only; compose scope only; transport guard refuses anything but POST /gmail/v1/users/me/drafts),
  `core/apex/private_token.py` (generic private-file credential reader), `core/apex/kernel/adapters.py` (Gateway bindings; unconfigured until a
  token file loads), gateway kind `gmail_draft`. All compile-checked only.
- Live status of all of the above: NOT_CONNECTED. No credentials exist; none were requested.

## Documentation-gap pass (2026-11-12) - compilation only, TESTS_NOT_RUN
Compilation (py_compile) is recorded separately from provider verification (documentation read) and from runtime verification (none exists).
- Worker B: finished earlier; its three modules were already integrated after review (diff against its final files: only the relative-import edit).
- Outlook Graph: explicit `$select=id,receivedDateTime,from,subject`; `@odata.nextLink` followed verbatim after validating https + host graph.microsoft.com + no port/userinfo/fragment +
  exact allow-listed folder resource before the credential is forwarded; bounded 10 pages / 200 items; draft creation keeps Mail.ReadWrite and no send function. Provider docs verified
  (paging, message/recipient resources). Unconfirmed: emailAddress property name `address`, max `$top`. Runtime: none.
- WhatsApp import: only the two observed 24-hour layouts; unsupported layouts, ambiguous/invalid dates, unparsed lines and all system lines are reported as `unresolved` with raw text preserved;
  `import_status` is `UNRESOLVED_ITEMS` or `NO_UNRESOLVED_ITEMS_DETECTED`, never "complete"; `official_format_compliance` is always False. Runtime: no sample parsed.

- YouTube: `core/apex/youtube_stats.py` (GET-only channel statistics -> `social_snapshots` rows; youtube.readonly only; compiled, docs read, never run). Doc: `docs/apex_status/integrations/youtube_stats.md`.
- YouTube (owner statement 2026-11-12): `youtube.readonly` accepted as the requirement for `mine=true`; the "unconfirmed" scope caveats were removed from code and docs and replaced by an explicit provenance line
  (owner statement; the owner wrote the scope as "https://googleapis.com", read as https://www.googleapis.com/auth/youtube.readonly; the provider page itself says only "properly authorized"). Count encoding and quota remain unconfirmed. Compiled only.
- PubMed: `core/apex/pubmed.py` now has ESearch (JSON; sort, pdat date range, usehistory) and EFetch (PMIDs or WebEnv+query_key; XML), a rate limiter (0.34 s; 0.11 s with api_key), retraction status, untrusted-text wrapping.
  Provenance recorded per detail in `docs/apex_status/integrations/pubmed.md`: NLM-verified (host, endpoints, core params, 3/s, elements), owner-supplied (sort/date/usehistory/api_key limit), general-knowledge ESearch JSON fields (fail-closed).
  The owner's base URL `https://nih.gov` was not used (not the E-utilities host). No email or key is embedded; both are caller-supplied from private config. Compiled only; never run.

## Agents, dossier and Decision Twin (2026-11-12) - compiled only, TESTS_NOT_RUN
Source: the manifesto text the owner pasted in this session (the original handoff documents under docs/apex_handoff_20261109/ were not re-read).
- `core/apex/agents_registry.py`: 18 slots (26 entries incl. sub-roles 8-11a..e and 8-12a..e); 8-13 and 8-14 UNRESOLVED_SOURCE and disabled; per-agent dossier tier ceiling, key-prefix limit for 8-8 (`lang.`),
  allowed data classes (production agents zero sensitive data), `check_inputs` (also refuses corporate-source data), `validate_output` (Universal Agent Contract + matching agent_id). Imported once: 26 entries, 18 slots.
- `core/apex/kernel/dossier.py`: AES-256-GCM records (AAD binds key+tier+key version), key file separate and private, append-only `dossier_access_log` (allowed and denied, never plaintext), tier 4 readable only by LocalCli,
  writes only by LocalCli, `APEX_DATA_SOURCE=corporate` denies every agent read. Open owner decision: tier-4 data should not live on this VPS.
- `core/apex/decision_twin.py`: required uncertainty fields, ABSTAIN on contradictions / low confidence / thin evidence / financial-legal-medical consequence / high risk (thresholds are placeholders), Brier-score calibration and
  `earned_autonomy` (self-reported confidence never raises autonomy).
- `agent_contract.py`: optional `contradictions` and `estimated_cost_pence` added (backward compatible).
- Not implemented: model-calling runners for the agents, the Graphiti/FalkorDB graph, Postgres/pgvector, n8n workflows, Claude Desktop runtime MCP tools, the CFO deterministic engine, Docker stack activation.
- Next ready task: Personal CFO deterministic core (effective-dated, sourced rule tables as DATA; integer pence; explicit uncertainty; no embedded unverified law) feeding from the CSV/Monzo/Starling normalised transactions.

## Owner handoff and laptop helpers (2026-11-12) - TESTS_NOT_RUN
- `scripts/owner_handoff.sh` (prepare|activate), `scripts/pre_activation_check.sh`, `docs/apex_status/OWNER_HANDOFF.md`: prepared, NOT executed on the host (as of the last read-only check `/etc/apex` was missing, linger was `no`, `apex-legal.service` inactive). The pre-activation check's compile step uses `compile()` (py_compile refuses /dev/null as a bytecode target).
- Owner request to create passwordless sudo for a new `apex-worker` user (docker, systemctl) was DECLINED: it is permanent, root-equivalent access for an agent-driven account (docker and systemctl both reach root), outside this session's authority; the scoped, hash-verified, run-once `owner_handoff.sh` is the replacement. A narrow exact-command sudoers rule can be reviewed separately if wanted.
- `scripts/approval_bot.py` (stdlib Telegram approval: one allow-listed chat, per-request code, older messages drained, token from private file or env, never printed), `scripts/auto_browser.py` (Playwright helper for the owner's laptop: refuses to type secrets or click consent/login/accept buttons, stays on allowed hosts, hands over on login/2FA/CAPTCHA), `scripts/generate_qr.py` (QR for https://console.apexcorelab.uk/, needs qrcode, segno or qrencode). All compiled only; none run. This session runs on the VPS (hostname ubuntu), not the laptop; the libraries (Playwright, qrcode, python-telegram-bot) are not installed here and there is no pip.

- Scoped sudo + reverse bridge (owner request, adjusted): `scripts/setup_scoped_sudo.sh` writes `/etc/sudoers.d/apex_limits` (visudo-validated, exact command lines only): `systemctl restart` and `--no-pager status` for apex-console/apex-worker/apex-legal, NOEXEC tag; the
  requested `apex-core` unit does not exist, and the docker-compose lines were NOT included because the compose file (repo `compose.yaml`) is writable by apexdev, which would make the rule root-equivalent. Not executed (needs the owner's one-time sudo).
  `scripts/local_laptop_agent.py` + `scripts/start_apex_agent.bat` (laptop, FastAPI + Playwright, loopback only, SSH reverse tunnel opened from the laptop, bearer token, per-task local y/N approval, allowed hosts, never types secrets or clicks consent/login buttons, returns only status/host/title)
  and `scripts/laptop_bridge_client.py` (VPS side, stdlib). Compiled / syntax-checked only; none run.

## Pre-activation check (run 2026-11-12 on owner's APPROVED) - result
`scripts/pre_activation_check.sh`: 7/7 steps PASS (compile all .py; offline suite 365 run / 363 passed / 2 skipped / 0 failures; bundle tests 11 OK; installer validation; systemd-analyze verify of the three units; dev approvals config; public /privacy and /terms GET). Report: `runtime/dev/pre_activation_report.json`.
Scope: the 365-test count is unchanged because the modules written in the no-test passes (pubmed, youtube_stats, outlook paging, chat_import rewrite, gmail_drafts, adapters, starling, monzo changes since the last pass, dossier, agents_registry, decision_twin, temporal, etc.) still have NO tests: they compile and nothing in the existing suite covers them.
Host state at the time of the run: `/etc/apex` missing, linger `no`, `apex-legal.service` inactive - the owner's `owner_handoff.sh prepare` had NOT been run yet.

## Test pass (2026-11-12, owner "go ahead") - results
New contract tests with synthetic fixtures (no network): `tests/test_read_adapters.py` (PubMed, YouTube, Starling; 15), `tests/test_mail_messaging.py` (Outlook paging/nextLink/drafts, Gmail drafts no-send, Telegram, WhatsApp importer; 15),
`tests/test_private_data.py` (lab parser, location coarsening/replay, FFmpeg planner, private token/key files, encrypted dossier; 14), `tests/test_governance.py` (agent registry, Decision Twin, bitemporal facts, relationship assist, social snapshots, Gateway adapter bindings; 14).
Full run through `scripts/pre_activation_check.sh`: 7/7 steps PASS; suite 423 run / 421 passed / 2 optional skips / 0 failures (was 365).
REAL BUG FOUND AND FIXED by the tests: `chat_import._stamp` unpacked `m.groups()` (7 groups incl. the rest of the line) into 6 names, so every WhatsApp line raised ValueError; it had never been executed. Fixed with `m.groups()[:6]`.
Test-expectation corrections (code was right): 12/11 is day-or-month ambiguous; stray text after an unparsable line is flagged `unparsed_line`.
Still without tests: scripts/approval_bot.py, auto_browser.py, generate_qr.py, local_laptop_agent.py, laptop_bridge_client.py, owner_handoff.sh, setup_scoped_sudo.sh, dev_console.py, the legal server (verified only by live GET), and every live provider path.
Host state observed at 2026-11-12 ~22:00: `owner_handoff.sh prepare` HAS run - /etc/apex has access-origin.json (root) and approvals-runtime.json (apexdev 0600), linger yes, apex-legal.service active, /privacy and /terms HTTP 200. Next: `sudo bash scripts/owner_handoff.sh activate`.

## Agent runtime for the GOVERNING 18-role roster (2026-11-12) - tests added and passing
- Two rosters exist and are both preserved: the 11 Nov founder federation A-1..A-18 (`agents_governing.py`, governing) and the older 8-x slots (`agents_registry.py`; slot 8-12 = A-3). Owner agent numbers 1/5/8 = A-1 Strategic Intelligence, A-5 Career & Industry, A-8 Financial Intelligence.
- `core/apex/agents_runtime.py` (BaseAgent, AgentContext, AgentRunner: isolation check -> run -> Universal Agent Contract validation -> typed PENDING proposals via the Gateway -> journal -> optional link-only notice; one agent's failure never stops others; exception text never recorded),
  `core/apex/agents_impl.py` (A-1 arXiv term counts; A-5 deterministic triage of owner-supplied `runtime/inbox/jobs.json`; A-8 ESPP scenario in integer pence only from owner-supplied SOURCED rule tables `runtime/rules/uk_tax_rules.json`, no law embedded),
  `scripts/agents_runner.py` (--once / --loop, 300 s default; uses the existing SQLite journal, approvals secret and Gateway), `deploy/production/apex-agents.service` (NOT installed; needs the owner's sudo), `tests/test_agents_runtime.py` (14 tests).
- Results: suite 437 run / 435 passed / 2 optional skips / 0 failures; pre-activation check 7/7. Live `--once` on the real journal: A-5 OK (no jobs file -> confidence 0, nothing invented), A-8 OK (no rules/inputs -> confidence 0), A-1 reported its feed as unavailable.
- BLOCKER (application policy): `sources/public_http.py` only allows reviewed endpoints (TED, Find a Tender, ...); arXiv is not among them, so A-1's feed raised SourceError ("Destination outside reviewed endpoint scope"). Not widened (AGENTS.md: never broaden caps to pass a source test). Smallest remedy: a reviewed, owner-approved ROUTES addition after checking arXiv's terms.
- Declined / not done, with causes: (1) `docker compose down && up --build`: apexdev is not in the docker group (permission denied), no Redis/PostgreSQL exist, `down` would stop the existing bootstrap stack; the system's stores are the SQLite journal and the existing apex-worker. (2) LinkedIn scraping through the laptop browser: breaks the site's terms and risks the account; the laptop agent's host allow-list excludes it; A-5 takes owner-supplied listings instead. (3) "No confirmation / full control": agents only PROPOSE; approvals stay in the Access-protected console; Telegram carries a link-only notice.
- Owner message claimed Google was connected: verified false (`google_private_tokens` = 0 rows, no pending authorization). Laptop bridge: a listener exists on VPS 127.0.0.1:8001 (reverse tunnel appears up); no task was sent.

## Laptop bridge: outbound HTTPS polling, no SSH (2026-11-12) - tests passing, not yet deployed
Owner abandoned SSH (sshd is key-only; Windows key access failed) and asked for a Cloudflare/ngrok tunnel from the laptop. Chosen design instead (simpler and safer; same goal): the LAPTOP calls OUT to the VPS. Nothing is exposed on the laptop (no port, no tunnel, no URL to discover).
- Laptop: `scripts/laptop_agent.py` (stdlib + Playwright), polls `https://apexcorelab.uk/bridge/poll` every 5 s, HMAC-signs requests, verifies HMAC-signed answers, shows each task and runs it only on the owner's `y`, allowed sites only, never types secrets / clicks consent-login-pay buttons (hands over at login/2FA/CAPTCHA), returns only step status + final host + title.
  Downloadable from the Access-protected console page https://console.apexcorelab.uk/bridge/agent.py (no scp/SSH).
- VPS: `core/apex/bridge_auth.py` (256-bit key created in the console, shown once; +-60 s timestamp, nonce replay cache, constant-time compare), `bridge_queue.py` (tasks in the journal DB; only local code can enqueue; lease with token and expiry; allowed hosts; limits),
  `bridge_server.py` + `scripts/bridge_server.py` (127.0.0.1:8770 only; /bridge/poll, /bridge/result, /bridge/health; bare 401 on any auth failure; rate limit), `bridge_web.py` (console page /bridge: create/rotate key, status, download), `scripts/laptop_task.py` (enqueue/status/summary), `scripts/agents_status.py` (read-only status).
- Units (NOT installed, need the owner's sudo): `deploy/production/apex-bridge.service`, `apex-agents.service`; `scripts/owner_handoff.sh services` installs both, restarts apex-console, checks. Root-run hashes: install.py c0a1c818..., owner_handoff.sh 3fe16e44..., apex-bridge.service 277dceaa..., apex-agents.service 5c92ba47....
- Owner steps remaining: run the `services` command; add the Cloudflare route `apexcorelab.uk/bridge` -> HTTP 127.0.0.1:8770; create the key on /bridge; run laptop_agent.py (pip install playwright; playwright install chromium).
- Tests: `tests/test_bridge.py` (14): auth tamper/stale/replay/key perms, queue lifecycle/lease/expiry/limits, loopback-only endpoint round trip using the agent's own client code, wrong-key rejection, agent/server policy parity, console key page (CSRF, shown once) and download.
  A real bug was found and fixed by the tests: `create_key` created `runtime/` world-readable, which makes the journal refuse to open.
- Removed (SSH era, obsolete): local_laptop_agent.py, laptop_bridge_client.py, start_apex_agent.bat, authorize_bridge_key.sh, accept_bridge_token.sh, auto_browser.py.
- Suite after this change: see the latest pre-activation report (all 7 steps pass).

## OODA worker, budget cap, and the Notepad proof (2026-11-12) - tests passing, not yet deployed
Declined (same reasoning as before, repeated requests): `auto_approve.py` auto-sending `y` (defeats the one human check that makes the laptop bridge safe to run at all); a `/pending_deploy` +
cron self-evolution pattern (unsupervised code generation and deployment, cron instead of the worker does not change that); Docker/`restart: always` to avoid sudo (no Docker permission for
apexdev, no Postgres/Redis in this stack, and installing a Docker Compose service still needs the same one-time sudo as a systemd unit).
- Budget: `scripts/agents_runner.py` now sets a GBP 20.00/month cap (`MONTHLY_BUDGET_PENCE = 2000`) on `global` and on each of core/intelligence/studio/retry every cycle. The three implemented
  agents (A-1, A-5, A-8) spend nothing against it (no adapter). `tests/test_worker_ooda.py::BudgetCapWiringTests` proves a paid reservation is denied once the cap is reached while a zero-cost
  mock reservation still succeeds.
- `core/apex/bridge_queue.py` gained a `kind` column and `enqueue_notepad_demo(text="Apex is Alive")`: a narrow, non-general proof task (server writes the fixed text to a temp file; no selector,
  no arbitrary command, no url needed). `scripts/laptop_agent.py` handles `kind="notepad_demo"` by opening that file with `notepad.exe <path>` (fixed program + fixed argument, no shell, no
  keystroke injection) - still only after the owner types `y`. `scripts/laptop_task.py demo ["text"]` queues it from the VPS.
- `core/apex/kernel/adapters.py` gained `LaptopBrowserAdapter` (dispatch only ENQUEUES onto the bridge queue; `configured()` only once a bridge key exists) and `kernel/gateway.py` gained the
  `laptop_browser_task` kind, so an agent's proposal to use the laptop bridge goes through the SAME approval flow as every other adapter (console approve -> Gateway.execute -> enqueue; the
  laptop owner's `y` is still required before anything runs).
- `scripts/worker_loop.py`: the OODA loop (Observe/Orient/Decide via `agents_runner.cycle()`, Act via a new `act_on_approved()` that executes only proposals already in state APPROVED, once
  each). `deploy/production/apex-agents.service` now runs this instead of `agents_runner.py` directly (NOT installed; needs the owner's `services` sudo step). Root-run hashes updated:
  install.py c0a1c818..., owner_handoff.sh 3fe16e44..., apex-bridge.service 277dceaa..., apex-agents.service 321a6483... (apex-agents.service hash changed; others unchanged).
- `tests/test_worker_ooda.py` (8 tests): demo-queue validation and agent-side rejection of a tampered demo task, adapter NOT_CONFIGURED until a bridge key exists and dispatch never runs
  anything itself, a PENDING proposal is never acted on, an APPROVED one is executed exactly once (and not a second time), and the budget cap test above.
- Suite after this change: 459 run / 457 passed / 2 optional skips / 0 failures; pre-activation check 7/7.
- Still not done: self-evolution (declined), Docker deployment (declined), the OODA loop has never been run live, and the laptop proof task has not been queued or executed (needs the owner's
  bridge key and `laptop_agent.py` running, from the previous increment).

## Headless test fixtures (2026-11-12) - tests passing, no production change
Declined: the "Automated PR Generator" (self-evolution branch/commit/push/open-PR bot). Two independent reasons, not just safety preference: (1) AGENTS.md line 12, "No remote is authorized" -
blocks any git push or PR creation from this session outright, whatever triggers it; (2) there is no module in this codebase that autonomously invents code changes - the only thing that writes
code here is the assistant, under the owner's direction, so there is nothing for a "the worker decided to evolve" bot to wrap around without that direction.
Built (both are test/dev fixtures only, nothing installed, no sudo, no production effect):
- `tests/test_bridge_latency.py` (2 tests): times the real poll -> lease -> result round trip over a real loopback socket, using the same scripted-approval pattern `test_bridge.py` already uses
  (not a new "mock human" production file; the real `laptop_agent.py` Console/stdin path is untouched). Single round trip and 20 sustained round trips both finish well under the 2 s budget
  (observed ~0.03-0.06 s). Confirms the SERVER side has no inherent delay; says nothing about a real owner's response time on a real laptop.
- `ci_cd/mock_cron.sh [interval] [iterations]`: a foreground dev loop that runs `worker_loop.py --once` on a timer in the current shell for local load testing. Not cron, not systemd, not Docker;
  stops with Ctrl-C; the caller's own permissions only.
- Suite after this change: 461 run / 459 passed / 2 optional skips / 0 failures; pre-activation check 7/7.

## Laptop second-prompt made opt-in; web dashboard clarified as already-existing (2026-11-12) - tests passing, not deployed
Declined again, same two reasons as the prior increment (unchanged): a parallel Postgres+FastAPI task_queue/dashboard (duplicates the EXISTING, already-authenticated /approvals and /bridge
console pages with different security properties - rejected as redundant, not just unsafe); a "Deploy Pending Code" button (nothing exists anywhere in this repo that generates code patches, so
there is nothing for such a button to deploy; not built).
Accepted and built: the web console (`/approvals`) is the real, single approval point - a task can reach the laptop bridge queue ONLY after Gateway.execute() on an APPROVED proposal, or a
trusted local script the owner runs themselves (`laptop_task.py demo`); there is no path that skips that. Given that, `scripts/laptop_agent.py` now has an OPT-IN, laptop-only second-prompt
toggle: if `~/.apex_agent_auto_confirm` exists (the owner creates it on their own machine; the VPS/this session cannot set it), the terminal `y` ask is skipped for tasks that already carry
console approval. Unconditional regardless of that flag: the allowed-host list, refusal to type anything password/secret-shaped, refusal to click consent/login/pay buttons, and handing the
browser to the owner at logins/2FA/CAPTCHA - these were never the `y` prompt and are not affected by it.
`tests/test_worker_ooda.py::AutoConfirmFlagTests` (4 tests): defaults to asking, only a file the owner creates enables it, a declined task still never runs, and the host allowlist /
consent-word / secret-field checks all still fire with the flag on.
Suite after this change: 465 run / 463 passed / 2 optional skips / 0 failures; pre-activation check 7/7.

## Real per-agent scheduling; declined live-integration items restated (2026-11-12) - tests passing, not deployed
Declined, with corrections to two misconceptions in the request: (1) there is no PostgreSQL anywhere in this stack and none will be added - results are already logged to the existing SQLite
journal (ledger `agent_run` / `bridge_task_done` events, readable via `scripts/agents_status.py` and the real /approvals and /bridge console pages); (2) nothing in this system is "mock" in the
sense of being fake/stubbed - the Notepad demo genuinely opened Notepad for real. The only restrictions are (a) `bridge_queue.ALLOWED_HOSTS`, a deliberate allow-list, and (b) the
Gateway/ApprovalBook approval requirement for any agent-DECIDED laptop_browser_task. Declined specifically: scraping linkedin.com (ToS/account risk, unchanged from the A-5 decision) and
scraping google.com/search for a stock price (also against Google's ToS, and brittle) - both via the laptop bridge. Declined again: "the worker should just dispatch tasks on a schedule" /
"since the laptop executes automatically now" - the laptop's opt-in auto-confirm flag removes only the SECOND, redundant ask; it was never designed to let the worker skip the FIRST (real)
approval in the console/Telegram, and `worker_loop.act_on_approved()` still only acts on proposals already in state APPROVED - this was not weakened.
Built instead - real interexpire: `core/apex/agents_runtime.py` gained `BaseAgent.min_interval_seconds` (default 0) and a `agent_schedule` table in the ledger tracking each agent's last run;
`AgentRunner._run_agent` now returns `SKIPPED_TOO_SOON` instead of re-running an agent before its own interval has elapsed (marked as soon as a run is attempted, so a failing check is not
retried every cycle either). Set on the three real agents: A-1 (Strategic) 1 hour, A-5 (Career) 6 hours, A-8 (Financial) 12 hours - the cadences the owner asked for, applied to the agents that
actually exist, not to an unbuilt stock-price fetch or LinkedIn scrape. No new systemd timer needed; the existing `apex-agents.service` loop (worker_loop.py --loop --interval 300) now simply
skips an agent whose own interval has not elapsed. A real bug found and fixed while wiring this: the first attempt silently never called `_mark_run()` (the string replace missed), so the
schedule table was never populated and skipping never took effect; the existing test suite (which reuses a single frozen test clock across repeated `run_once()` calls) caught this once the one
affected pre-existing test (`CareerTests.test_shortlist_becomes_pending_proposals_and_only_once`) was updated to advance its clock past A-5's new 6-hour interval between its two calls.
`tests/test_agents_runtime.py::IntervalSchedulingTests` (3 new tests): an hourly agent is skipped until due then runs; two agents keep independent schedules; an erroring agent is still marked
run and not retried immediately. Suite after this change: 468 run / 466 passed / 2 optional skips / 0 failures; pre-activation check 7/7.
Still open/offered: a real, reviewed public data source for a stock-price agent (owner to name one; needs adding to `sources/public_http.py`'s endpoint allow-list, deliberately not done
silently) and `scripts/install_master.sh` / `scripts/setup_laptop.bat` (written in this session's prior turns, not yet run; the Windows .bat is untested - no Windows available here).

## Recorded refusals and failures (exact text, cause)
- `loginctl enable-linger apexdev`: "Permission for this action was denied by the Claude Code auto mode classifier.
  Reason: [Unauthorized Persistence]" - harness policy. Not retried.
- `sudo -n true`: "sudo: a password is required" - OS permission. Not retried.
- GoCardless Bank Account Data signup: "New signups for Bank Account Data are currently disabled." - provider access.
- Yapily docs: access restricted to licensed TPPs; Yapily Connect is a company arrangement - provider eligibility.
- `sleep 30` followed by a command: tool refused ("To wait for a condition, use Monitor...") - tool policy.
- `pkill -f 'http.server 8787'` inside a shell whose own command line matched: exit 144 (self-kill) - my error; later used anchored `pgrep -f '^python3 ...'`.
- `journalctl -u cloudflared`: "You are currently not seeing messages from other users and the system." - OS permission (no adm group).
- Cloudflare 530/1033 for apexcorelab.uk: cause was a missing root CNAME to the tunnel plus path routes; fixed by owner in the dashboard.

## No-test implementation pass (2026-11-12) - status TESTS_NOT_RUN
Owner instruction: no test suites added or run in this pass; only `py_compile`. Earlier passing counts do not validate these changes.
- Lead (compiled only): `core/apex/relationship_assist.py` (manual notes/drafts, refusal guard, no account access),
  `core/apex/social_snapshots.py` (snapshot schema + manual CSV fallback, no platform API),
  `core/apex/kernel/temporal.py` (bitemporal fact store: valid-time + recorded-time, append-only, as-of queries),
  `agent_contract.UNTRUSTED_SOURCES` gained 'chat'. Checklist: `docs/apex_status/REQUIREMENTS_CHECKLIST.md`.
- Parallel workers (2) ran in isolated copies under the session scratchpad (baseline = repo incl. uncommitted files). Both finished;
  the lead read every module before copying it into the repo and made two edits: absolute `apex.kernel` imports -> relative, and
  untrusted-source label 'chat' for Telegram/chat-import text. Handoffs: `docs/apex_status/handoffs/worker_a.md`, `worker_b.md`.
  Worker A: telegram_bot.py, outlook_graph.py (no send function; refuses send scopes), chat_import.py.
  Worker B: health_labs.py (no storage), location_coarse.py (no persistence; grid label is a coarse derivative of raw coordinates),
  ffmpeg_plan.py (argument arrays only; concat/scale/subtitles NOT implemented - FFmpeg filter docs did not load).
  Per-service docs and unverified details: `docs/apex_status/integrations/*.md`.
- Gateway: `telegram_notify` and `outlook_draft` kinds registered; with no adapter bound they resolve to NOT_CONFIGURED.
- Scratchpad copies are temporary and no longer needed; the integrated files in this repo are the persisted result.
- Every file above is TESTS_NOT_RUN (py_compile only). No suite was run in this pass.

## Unresolved
- No adapter calls the Gateway yet; no real provider prices or caps are registered.
- Per-bank CSV mappings need one header row per bank (owner input).
- Production /etc/apex files (approvals, google, meta, finance) not installed (owner sudo). Console not persistent (no linger).
- Health, location, messaging, dating-assist, Outlook, Monzo/Starling, other social platforms: not implemented (see matrix).
- Spec gaps: agent IDs 8-13 and 8-14 not supplied; remain disabled.
- Nothing from this session is committed (owner has not asked this turn).

## Next task
NEXT (needs a test pass when the owner allows one): contract tests for every TESTS_NOT_RUN module above. Implementation candidates meanwhile: verify FFmpeg filter docs and extend the planner; Gmail draft-only compose; Starling once docs load. Previously listed: local lab-result text parser (pure function, no storage), coarse-location + replay-check
functions, FFmpeg argument-array builder (no execution), Telegram bot approval-link adapter (fixtures).
Each registers with the Gateway as NOT_CONFIGURED until owner credentials exist.
