# Worker fairness and infrastructure recheck

Entry commit ad6bd94 on apex/unified-field-integration. Original manifesto SHA256
3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd unchanged.

Implemented and tested: persistent rotating mission admission in worker.py.
Previously the first four blocked graphs starved all later work on every cycle.
Now each cycle admits at most four unfinished graphs after the durable cursor,
wrapping at the end. Schedule diagnostics do not consume mission capacity.
Cursor advancement and admission receipt are one SQLite transaction. Admission
is explicitly not execution; existing job leases and fencing remain authoritative.
A crash after admission defers that batch by one rotation, without losing jobs.
No original mission, schedule, source evidence or job receipt was rewritten.

Tests: baseline 195 run /193 pass /2 optional dependency skips. Final 200 run /
198 pass /2 skips /0 failures or errors. Added starvation, reconnect, SystemExit,
actual forked-process os._exit, audit failure rollback and STOP cursor checks.
The adversarial workload is a synthetic control regression, not an independent
real-world utility benchmark. Existing crash, security and recovery tests remain.
Local live ledger audit verified77 events before edits; source tracing retained
178 groups /968 units. These are not full manifesto acceptance.

Infrastructure: system cloudflared loaded/active/running, superseding the earlier
blanket unavailable-service statement. Tunnel connectivity and its identity were
not verified. console.apexcorelab.uk returned NXDOMAIN through the current DNS
resolver. User systemd bus unavailable. System installation remains blocked by
sudo no-new-privileges and absence of an approved privileged administration tool.
No sandbox bypass, service change, credential disclosure or public deployment.
A rotated scoped Cloudflare management binding, owner Access identity/policy,
production origin authorization and verified DNS/TLS are still required.

Remaining engineering is substantial: bounded parallel workers, production origin
authentication, independent research and benchmark, complete source-backed provider
inventory, 18 executable specialist capabilities and full acceptance are incomplete.
Two adapters have historical live evidence; no new live provider verification here.
No verified income, no new field trace, no API spend. Full target remains binding.

Rollback: revert this increment's code only; leave historical ledgers untouched.
The additive worker_dispatch table can remain unused on rollback. Do not reset
historical code fingerprints to force old missions to execute. Re-review and submit
new mission/schedule identities against changed code.
