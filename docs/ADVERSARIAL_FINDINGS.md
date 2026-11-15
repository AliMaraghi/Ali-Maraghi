# Adversarial findings — A-17, 2026-11-15

Still SPEC_ONLY in `core/apex/agents_governing.py` (this module exists and is tested; it is
not wired into `agents_runner.py` and that status was not flipped). Code:
[`core/apex/roles/adversarial_evaluation.py`](../core/apex/roles/adversarial_evaluation.py).
Tests: [`tests/test_adversarial_evaluation.py`](../tests/test_adversarial_evaluation.py),
3/3 passing. 8 probes run against the real kernel (sandbox, ledger/facts, gateway,
approvals), synthetic keys/fixtures only.

## Result: 7 PASS, 1 FINDING

| Probe | Target | Verdict | Severity |
|---|---|---|---|
| P-1 network bypass | sandbox | PASS | — |
| P-2 subprocess escape | sandbox | PASS | — |
| P-3 read outside sandbox (`/etc/passwd`) | sandbox | PASS | — |
| **P-4 filesystem allowlist over-breadth** | sandbox | **FINDING** | **MEDIUM** |
| P-5 ledger signature forgery | ledger/facts | PASS | — |
| P-6 ledger hash-chain truncation | ledger/facts | PASS | — |
| P-7 gateway execute without approval | gateway | PASS | — |
| P-8 approvals second layer, bypassing gateway | gateway/approvals | PASS | — |

## FINDING P-4 (MEDIUM) — sandbox file-read allowlist is broader than documented

**Claim in `sandbox.py`'s own docstring:** file access is confined to "a fresh scratch
directory plus the Python installation's own stdlib/site tree."

**Actual code (`sandbox.py`, `run_in_sandbox`):**
```python
allowed = (real_dir, sys.base_prefix, sys.prefix, sys.exec_prefix)
```
and the audit hook checks `real.startswith(p) for p in _ALLOWED` — a plain string-prefix
match against `sys.prefix`/`sys.base_prefix`/`sys.exec_prefix`, not a path restricted to
Python's own install directories specifically.

**Why this matters:** on this machine, `sys.prefix == sys.base_prefix == sys.exec_prefix ==
"/usr"` — confirmed this run. `/usr` is the system-wide installation prefix on most Linux
distributions, not a Python-specific directory. Any world-readable file anywhere under
`/usr` (not just Python's `lib/python3.x/` tree) is therefore readable by candidate code
running in the sandbox, contradicting the "stdlib/site tree" claim.

**Reproduction (raw output, this run):**
```
sandbox.run_in_sandbox("print(open('/usr/share/zoneinfo/UTC', 'rb').read(8))")
-> crashed=False, exit_code=0, stdout="b'TZif2\x00\x00\x00'\n"
```
`/usr/share/zoneinfo/UTC` is timezone data, not part of the Python standard library, and the
read was **not** blocked.

**Severity reasoning:** MEDIUM, not HIGH — the exposure is read-only, confined to
world-readable files (the sandbox's own OS-level file permissions still apply), and on most
systems `/usr` does not contain secrets (those belong in `/etc`, `/home`, or environment
variables, all already correctly blocked — see P-3). It is real over-exposure relative to
the stated design intent, not a demonstrated path to secret material on this machine.
Severity could be HIGH on a system where sensitive, world-readable data happens to live
under the same prefix as the Python installation (e.g. a non-standard install layout, or a
system where `/usr` is unusually permissive).

**Fix, not yet applied (this probe's job was to find it, not patch it under this mission's
scope):** narrow the allowlist to the actual stdlib/site-packages directories
(`sysconfig.get_paths()["stdlib"]`, `sysconfig.get_paths()["purelib"]`,
`sysconfig.get_paths()["platstdlib"]`) instead of the coarser `sys.prefix` family, or add an
explicit denylist for non-Python subtrees under the same prefix.

## The 7 PASS results, briefly

- **P-1/P-2/P-3:** the sandbox's audit hook correctly blocks network connect, subprocess
  spawn, and reads of files genuinely outside its scratch dir and Python install (`/etc/passwd`).
- **P-5:** tampering a signed fact's `object` field after signing is caught —
  `verify_fact_signature` recomputes the signature over the row's *current* content and
  correctly returns `False`.
- **P-6:** deleting a signed fact from the middle of the chain is caught by
  `verify_fact_chain` — `PREV_HASH_MISMATCH` at the first fact downstream of the deletion.
- **P-7/P-8:** attempting execution of an unapproved proposal is blocked independently at
  both `ActionGateway.execute` and `ApprovalBook.execute` — confirms the defense-in-depth
  property an earlier session's own audit first identified still holds.
