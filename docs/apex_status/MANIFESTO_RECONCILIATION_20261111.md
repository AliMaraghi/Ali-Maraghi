# Manifesto reconciliation gate — 2026-11-11

Status: BLOCKED_SOURCE_NOT_SUPPLIED. No architectural change made under this directive.

Protected source present: docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md
dated 8 Nov 2026, SHA-256 3947a6b6...1bcd (matches pin; review-kit copy identical).
No 11 Nov 2026 "Final Master Edition" exists on this host (repo, ~/Documents searched).

Directive vs pinned text (line numbers in pinned file):
- n8n: pinned `docker.n8n.io/n8nio/n8n:2.46.6` + digest lock (54, 439); "1.70.0" absent.
- Autonomy: engine L1-L6 (270); L1-L4 only in health appendix (334-).
- Budget: per-call..project hard budgets (64); no "£20/month" figure.
- Present: Redis 7+ queue mode (55), PostgreSQL 15+ with pgvector (56), Universal Agent
  Contract, Action Gateway, Decision Twin, Self-Evolution, isolated personal dossier (§12),
  18-agent federation (§8), cinematic factory (§18), Command Centre PWA (appendix B).
- Absent by those names: FastAPI, MCP, "Sovereign Dossier", "Knowledge Graph" (Persian
  "گراف شواهد" present), "Cinematic Studio".

Next exact operation: owner places the 11 Nov source file on the host; then
store byte-exact under docs/apex_handoff_20261111/, record SHA-256, mark read-only,
diff against the 8 Nov edition, and re-run reconciliation. Neither edition is altered.

Database: current runtime is the SQLite Ledger (runtime/kernel.sqlite3). PostgreSQL/Redis/n8n
require new services (Docker or packages) and a reviewed, reversible migration with founder
approval; nothing migrated. Existing ledger, receipts and history preserved.
