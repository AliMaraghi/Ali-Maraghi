# Conflict register — 8 Nov edition vs 11 Nov founder upload (appendix ج rule 3)

Both texts preserved unmodified:
- docs/apex_handoff_20261109/APEX_4_4_FINAL_MASTER_MANIFESTO.md sha256 3947a6b6…1bcd (842 lines)
- docs/apex_handoff_20261111/APEX_4_4_MANIFESTO_20261111_FOUNDER_UPLOAD.md sha256 5af960fd…013f (160 lines, signed)
Rule: historical text is not deleted; the later ratified decision governs current execution;
rule 4 scope (sections 0-18, 18 agents, OWP, UK CFO, cinema, self-evolution, longevity) is retained.

| # | Topic | 8 Nov | 11 Nov (governs) | Execution consequence |
|---|---|---|---|---|
| C1 | n8n pin | 2.46.6 + digest (54, 439) | 1.70.0 (13) | 1.70.0 has published critical RCEs (e.g. CVE-2026-21877 <1.121.3; CVE-2026-33660/33696 <1.123.27). NOT deployed. Founder must approve a patched pin (>=1.123.27 or >=2.13.3, verified tag+digest). |
| C2 | Autonomy | L1-L6 (270) | L1-L4 (114) | L1-L4 governs; L5/L6 history kept. |
| C3 | Budget | multi-level hard budgets (64) | £20/month API cap, auto-stop (15) | Compatible; current zero budget is stricter until a paid API key is approved. |
| C4 | 18 agents | World Monitor … Viral Detector (219-236) | Strategic Intelligence … Self-Evolution & Systems (69-86) | 11 Nov roster governs; 8 Nov capabilities retained as functions to map, not deleted. |
| C5 | Banking source | (aggregator unspecified) | TrueLayer (90) | TrueLayer adapter kept; live needs TrueLayer commercial go-live. Enable Banking (finance.py) is an engineering deviation chosen for personal eligibility: founder ruling required. |
| C6 | Key custody | encrypted stores | AES-256 keys off-server (109) | Current Fernet keys live in /etc/apex on server: redesign required (e.g. founder-held key unwrap at start). |
| C7 | HITL channel | dashboard | Telegram or dashboard (104) | Telegram absent. |
| C8 | Publishing | queues | Buffer API (126) | Not implemented; external writes need HITL. |
| C9 | Sandbox | sandbox | Docker sandbox (138) | AGENTS.md requires approval for Docker. |
