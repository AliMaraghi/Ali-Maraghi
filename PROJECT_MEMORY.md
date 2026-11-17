# APEX - project memory (read this first)

Last updated: 2026-11-17. Written from the code on branch `apex/unified-field-integration`
(base commit `d463b1d`) plus the uncommitted work listed under "Pending". Nothing in this file
was verified against the live server. If this file and the code disagree, the code wins - fix
this file.

## 1. What APEX is today

A single-owner assistant. A React/Three.js voice-and-avatar web UI talks to one small Python
service that routes each message to a fixed menu of reviewed handlers:

- Dating drafts: 3 opening messages from a profile bio the owner pastes. Text only, never sent.
- Tweet drafts: text only, never posted.
- Academic news: live titles from allowlisted arXiv / MIT News feeds.
- Finance scenario: ESPP / UK tax / UC / mortgage arithmetic on owner-supplied input files,
  plus one short LLM-phrased recommendation (decision support, not advice).
- Job shortlist report, PubMed research queue, system status.
- Statement CSV parser (`core/apex/finance.py: parse_statement`): exists as code, has no UI.
- ReAct agent loop (`core/apex/agent_loop.py`) and daily briefing
  (`scripts/run_autonomous_agent.py`): PENDING, see section 6.

It is not the four-layer, 18-agent system in the founder manifesto. The manifesto
(`docs/apex_handoff_20261109/`) remains the immutable long-term requirement; see `AGENTS.md`.

## 2. Architecture state

- Backend: `scripts/voice_api.py`, plain WSGI served by waitress on 127.0.0.1:8000
  (`apex-voice.service`). It is NOT FastAPI - do not "fix" it into uvicorn.
- Frontend: `apex-ui/` (React 18 + Vite 5), built to `apex-ui/dist/`, served by `serve_ui.py`
  on port 8081 (`apex-ui.service`), public at `ui.apexcorelab.uk`; API at `api.apexcorelab.uk`.
- Data: SQLite, `runtime/kernel.sqlite3` - an append-only, hash-chained ledger plus budget,
  approvals and conversation tables. `runtime/` is git-ignored and exists only on the server.
- Secrets: `/etc/apex/anthropic-key`, `/etc/apex/approvals-runtime.json` (mode 0600, never in Git).
- Scheduled agents: `apex-agents.service` (`scripts/worker_loop.py`), nightly user timer in
  `deploy/user/`.
- Server: Ubuntu 24.04 VPS, repo at `/home/apexdev/apex-work`, behind Cloudflare.

## 3. What works (in code; re-verify live before claiming)

- `POST /api/chat`, `GET /api/dashboard`, `GET /api/agent_telemetry` (alias `/api/telemetry`).
- Every LLM call is reserved against `apex.kernel.budget.Budget`. No price or no daily cap
  means HTTP 402 / BUDGET_DENIED. Zero budget by default.
- Side-effecting actions go through `apex.kernel.approvals.ApprovalBook` (PENDING -> human
  approval in the console approvals page). Agents propose; they do not execute.
- Offline suite: `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_offline.py`.

## 4. Known open items

- `apex-ui.service` binds 0.0.0.0:8081 and Cloudflare Access on the UI is unresolved
  (`deploy_final.sh` notes). Until fixed, do not describe the UI as access-controlled.
- Banking card reports "Needs setup": no aggregator chosen, no web route.
- The React dashboard has no Approve button; approvals live in the console page only.
- Recurring `dist/` permission problem: caused by running git/npm as root. Always run them
  as `apexdev`.

## 5. What is banned (do not build, do not re-propose)

- No autonomous execution of trades, payments or any money movement.
- No dating automation: no swiping, logging in, scraping, sending or impersonation on any
  dating platform. Drafts for the owner to send by hand only.
- No automatic posting, emailing or messaging anywhere. Drafts and proposals only.
- No bank connection outside an FCA-authorised aggregator with the owner's own consent flow;
  no screen-scraping, no stored bank passwords. Payment initiation stays blocked in code.
- No account numbers, sort codes, statements, credentials or `runtime/` content in Git, logs,
  or prompts. Statement tools pass aggregates only.
- No unpriced or uncapped LLM spend. No self-modification outside reviewed, tested commits.
- Never report a connector, agent or deployment as working without live evidence.

## 6. Pending (written and tested offline on 2026-11-17, NOT committed, NOT deployed)

- `core/apex/agent_loop.py`, `scripts/run_autonomous_agent.py`,
  `deploy/user/apex-briefing.{service,timer}` (07:00 Europe/London). Needs: the SKU priced
  once (`--set-price`), a daily cap on pool `core`, and owner inputs in
  `runtime/inbox/statements/*.csv` and `runtime/inbox/dating_profiles.json`.
- Dashboard shows the latest briefing (`orchestrator.dashboard_payload` -> `briefing`).
- PWA: `apex-ui/public/manifest.json`, `sw.js`, icons; registered in `src/main.jsx`.
- `scripts/backup_sqlite.py`: consistent nightly snapshot to `backups/`, 14-day retention.
  Same-disk only; copy off the server for real protection.
- Offline suite after these changes: 774 passed, 7 failed in `test_dev_config`,
  `test_access_refresher`, `test_adversarial_evaluation`. The same 7 fail on a clean
  checkout of `d463b1d` in the same sandbox (run as root), so they predate this work.

### Local-model mode (added 2026-11-17, same status: tested offline, NOT deployed)

- `APEX_LLM_PROVIDER=ollama` routes every LLM call to a local Ollama server
  (`core/apex/local_llm.py`); no hosted key is read. The server URL must be loopback/private.
- Default models are sized for the CPU-only 8 GB VPS: chat `qwen3:4b`, embeddings `bge-m3`.
  A 4B model is below the level where open models drive tools reliably - expect wrong or
  malformed steps and slow replies. With a 24 GB GPU use `qwen3.6:27b` instead (one env var).
- Semantic memory (`core/apex/semantic_memory.py`): table `memory_items` in the same SQLite
  file, indexed with sqlite-vec when the extension loads, exact Python scan when it does not
  (the VPS has no pip). Holds conversation turns, briefings, notes. Bank transactions are
  deliberately NOT embedded - they stay structured and exact.
- Tested only against a stand-in HTTP server that mimics Ollama's `/api/chat` and
  `/api/embed`. Never yet run against a real Ollama model.
- Two ways to run: `install_apex.sh` (VPS, existing systemd services, no Docker) or
  `docker-compose.local.yml` (UI + backend + daily agent + Ollama in containers).
- In local mode the installer prices all LLM SKUs at zero. BEFORE switching back to a hosted
  API, re-price them (`voice_api.py --set-daily-cap-pence N`, `run_autonomous_agent.py
  --set-price`) or hosted spend would be uncapped.
- Do not run someone else's "one-shot installer" that clones a second copy to /opt, rewrites
  `apex-voice.service` to run as root, or opens a public port for the UI. The live data is in
  `/home/apexdev/apex-work/runtime` and must stay the only copy in service.

### Opportunity Scouts and monthly hard cap (added 2026-11-17; tested offline, NOT deployed)

- Scouts (`core/apex/scout_events.py`, `scout_wealth.py`, runner `scripts/run_scouts.py`,
  timer `deploy/user/apex-scout.timer`, every 4 hours). Read-only. Events come from the public
  iCal feeds of Meetup groups the owner lists in `runtime/inbox/scout_config.json`; jobs from
  Reed's official API (needs a free key in `/etc/apex/reed-api-key`); one headline from BBC
  Business RSS. None of these feeds has been fetched live from this code yet.
- Eventbrite is deliberately absent: it has no public search API, and scraping it breaks its
  terms. Do not add a scraper.
- The model only ranks and phrases. Code picks the best-paid job, checks every index, and
  drops any model sentence containing a number that was not in the fetched data or buy/sell
  wording. Nothing the scouts find is acted on.
- Hard cap: `MONTHLY_HARD_CAP_PENCE = 2000` in `core/apex/kernel/budget.py`, enforced inside
  `Budget.reserve` for every pool and provider (`HardBudgetExceeded`). It bounds what the
  ledger reserves at owner-set per-call estimates; it is not a meter on the provider's real
  bill. The true backstop is a spend limit or prepaid balance at the provider.
- `core/apex/gpu_controller.py`: reserve-then-start, watchdog, always-destroy, orphan alarm.
  Tested with a fake provider only. The RunPod v2 adapter is untested and nothing calls it.
  Do not route bank data or profiles to a rented GPU without the owner deciding that knowingly.

## 7. How to resume

1. Tell the AI: "Read PROJECT_MEMORY.md and AGENTS.md first, then `git log -15` and
   `git status`."
2. Confirm what is actually live before changing anything: service status, `/api/dashboard`.
3. Work as `apexdev`, on a branch, with the offline suite green before any deploy.
4. Update this file in the same commit as any change to sections 1-6.
