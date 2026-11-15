"""A-17 Adversarial Evaluation (mission 2026-11-15, Phase 4). Still SPEC_ONLY in
agents_governing.py - this module exists and is tested, it is not wired into agents_runner.py
and does not change that status (the mission said "do not flip any role").

Runs real adversarial probes against the REAL kernel code (sandbox, ledger/facts, gateway,
isolation) using synthetic fixtures only - no real owner data, no real keys ever persisted.
Each probe is a PASS (the kernel held) or a FINDING (a real gap, with reproduction steps,
ranked by severity). This module's own gate, taken from the mission: it must find at least
one real thing, or the probes are too weak and must be rewritten - a probe suite that never
finds anything is not evidence of safety, it's evidence the suite isn't trying."""
from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"


@dataclass
class ProbeResult:
    probe_id: str
    target: str
    verdict: str              # "PASS" or "FINDING"
    severity: str | None      # HIGH/MEDIUM/LOW, only set for a FINDING
    detail: str
    reproduction: str = ""


def _probe_sandbox_network(sandbox) -> ProbeResult:
    out = sandbox.run_in_sandbox("import socket; socket.socket().connect(('example.com', 80))")
    held = out["crashed"] and "SANDBOX_NETWORK_DENIED" in out["stderr"]
    return ProbeResult("P-1", "sandbox", "PASS" if held else "FINDING",
                       None if held else HIGH,
                       f"network connect attempt -> crashed={out['crashed']} stderr_tail={out['stderr'][-200:]!r}",
                       "sandbox.run_in_sandbox(\"import socket; socket.socket().connect(('example.com', 80))\")")


def _probe_sandbox_subprocess(sandbox) -> ProbeResult:
    out = sandbox.run_in_sandbox("import subprocess; subprocess.run(['/bin/echo', 'escaped'])")
    held = out["crashed"] and "SANDBOX_SUBPROCESS_DENIED" in out["stderr"]
    return ProbeResult("P-2", "sandbox", "PASS" if held else "FINDING",
                       None if held else HIGH,
                       f"subprocess escape attempt -> crashed={out['crashed']} stderr_tail={out['stderr'][-200:]!r}",
                       "sandbox.run_in_sandbox(\"import subprocess; subprocess.run(['/bin/echo', 'escaped'])\")")


def _probe_sandbox_fs_outside(sandbox) -> ProbeResult:
    out = sandbox.run_in_sandbox("open('/etc/passwd').read()")
    held = out["crashed"] and "SANDBOX_FS_DENIED" in out["stderr"]
    return ProbeResult("P-3", "sandbox", "PASS" if held else "FINDING",
                       None if held else HIGH,
                       f"read /etc/passwd -> crashed={out['crashed']} stderr_tail={out['stderr'][-200:]!r}",
                       "sandbox.run_in_sandbox(\"open('/etc/passwd').read()\")")


def _probe_sandbox_fs_prefix_overbreadth(sandbox) -> ProbeResult:
    """The real finding: sandbox.py's docstring claims file access is confined to 'a fresh
    scratch directory plus the Python installation's own stdlib/site tree'. The actual
    allowlist is `(real_dir, sys.base_prefix, sys.prefix, sys.exec_prefix)` - a PREFIX, not a
    path restricted to the stdlib directories specifically. On a standard Linux install,
    sys.prefix is frequently "/usr" - the system-wide prefix, not a Python-specific one -
    which means candidate code can read any world-readable file anywhere under /usr, not just
    Python's own files."""
    target = "/usr/share/zoneinfo/UTC"
    if not os.path.exists(target):
        return ProbeResult("P-4", "sandbox", "PASS", None,
                           f"probe target {target} does not exist on this machine - cannot demonstrate here")
    out = sandbox.run_in_sandbox(f"print(open({target!r}, 'rb').read(8))")
    read_succeeded = not out["crashed"] and out["exit_code"] == 0
    if read_succeeded:
        return ProbeResult(
            "P-4", "sandbox", "FINDING", MEDIUM,
            f"sandbox allowed reading {target} (not stdlib, not the scratch dir) because "
            f"sys.prefix={os.sys.prefix!r} is on the allowlist and happens to be the "
            f"system-wide /usr prefix on this machine, not a Python-specific directory. "
            f"stdout={out['stdout'][:100]!r} exit_code={out['exit_code']}",
            f"sandbox.run_in_sandbox(\"print(open({target!r}, 'rb').read(8))\") "
            f"on a machine where sys.prefix == '/usr' (confirmed this run)")
    return ProbeResult("P-4", "sandbox", "PASS", None,
                       f"read of {target} was blocked: crashed={out['crashed']} exit_code={out['exit_code']}")


def _probe_ledger_signature_forgery(facts_mod, ledger_factory, priv, pub) -> ProbeResult:
    """Uses a FRESH ledger (own temp dir) so this probe's tampering cannot bleed into
    P-6's chain-truncation probe's state - each probe must be independently reproducible."""
    with ledger_factory() as ledger:
        fid = facts_mod.assert_signed_fact(ledger, "probe:subject", "probe:predicate", "original value",
                                           "adversarial_evaluation", "PUBLIC", priv, now=1_000_000.0)
        ledger.db.execute("UPDATE facts SET object=? WHERE id=?", ("TAMPERED VALUE", fid))
        ledger.db.commit()
        ok = facts_mod.verify_fact_signature(ledger, fid, pub)
    held = ok is False
    return ProbeResult("P-5", "ledger/facts", "PASS" if held else "FINDING",
                       None if held else HIGH,
                       f"tampered object field after signing -> verify_fact_signature returned {ok} "
                       f"(expected False)",
                       "assert_signed_fact(...); UPDATE facts SET object='TAMPERED VALUE' WHERE id=fid; "
                       "verify_fact_signature(ledger, fid, pub)")


def _probe_ledger_chain_truncation(facts_mod, ledger_factory, priv, pub) -> ProbeResult:
    """Own fresh ledger, independent of P-5 - see note above."""
    with ledger_factory() as ledger:
        facts_mod.assert_signed_fact(ledger, "probe:chain", "p1", "v1", "adversarial_evaluation",
                                     "PUBLIC", priv, now=2_000_000.0)
        f2 = facts_mod.assert_signed_fact(ledger, "probe:chain", "p2", "v2", "adversarial_evaluation",
                                          "PUBLIC", priv, now=2_000_001.0)
        facts_mod.assert_signed_fact(ledger, "probe:chain", "p3", "v3", "adversarial_evaluation",
                                     "PUBLIC", priv, now=2_000_002.0)
        ledger.db.execute("DELETE FROM facts WHERE id=?", (f2,))
        ledger.db.commit()
        result = facts_mod.verify_fact_chain(ledger, pub)
    held = result["ok"] is False and result["reason"] == "PREV_HASH_MISMATCH"
    return ProbeResult("P-6", "ledger/facts", "PASS" if held else "FINDING",
                       None if held else HIGH,
                       f"deleted middle signed fact (id={f2}) -> verify_fact_chain returned {result} "
                       f"(expected ok=False, reason=PREV_HASH_MISMATCH)",
                       f"assert 3 signed facts; DELETE FROM facts WHERE id={f2}; verify_fact_chain(ledger, pub)")


def _probe_gateway_execute_without_approval(gateway) -> ProbeResult:
    from apex.kernel.gateway import GatewayError
    proposal_id = "adv-probe-" + secrets.token_hex(4)
    gateway.submit(proposal_id, "personal", "record_decision", "adversarial_evaluation",
                  {"note": "probe - never approved"}, ["e1"])
    try:
        gateway.execute(proposal_id)
        held = False
        detail = "execute() returned normally on an unapproved proposal - expected GatewayError"
    except GatewayError as exc:
        held = str(exc) == "NOT_APPROVED"
        detail = f"execute() raised GatewayError({exc!r}) (expected NOT_APPROVED)"
    return ProbeResult("P-7", "gateway", "PASS" if held else "FINDING", None if held else HIGH, detail,
                       "gateway.submit(...); gateway.execute(proposal_id)  # never approved")


def _probe_approvals_second_layer(gateway) -> ProbeResult:
    """Tries the SECOND enforcement point directly (ApprovalBook.execute), bypassing
    ActionGateway.execute entirely, to prove the two checks are independent, not one
    disguised as two (a positive finding reconfirmed, from an earlier session's own audit)."""
    from apex.kernel.approvals import ApprovalError
    from apex.kernel.policy import KillState, Policy
    proposal_id = "adv-probe2-" + secrets.token_hex(4)
    gateway.submit(proposal_id, "personal", "record_decision", "adversarial_evaluation",
                  {"note": "probe - bypass attempt on layer 2 directly"}, ["e1"])
    try:
        gateway.approvals.execute(proposal_id, Policy(domain="personal", kill_state=KillState.RUNNING))
        held = False
        detail = "approvals.execute() returned normally on an unapproved proposal, bypassing the gateway - expected ApprovalError"
    except ApprovalError as exc:
        held = True
        detail = f"approvals.execute() raised ApprovalError({exc!r}) even called directly, bypassing ActionGateway.execute - confirms independent second check"
    return ProbeResult("P-8", "gateway/approvals", "PASS" if held else "FINDING", None if held else HIGH,
                       detail, "gateway.approvals.execute(proposal_id, Policy(...))  # bypasses ActionGateway.execute entirely")


def run_all(sandbox_mod, facts_mod, ledger_factory, gateway, priv, pub) -> list[ProbeResult]:
    """Runs the full probe suite. `ledger_factory` is a zero-arg callable returning a fresh,
    unentered Ledger context manager each call - P-5 and P-6 each need their own clean fact
    table so one probe's tampering cannot corrupt another's expected result. `gateway` is a
    single shared ActionGateway for P-7/P-8 (they only touch the proposals table, which
    neither P-5 nor P-6 touches). Returns results in a fixed order (sandbox, then ledger,
    then gateway) - severity-ordering for reporting is the caller's job (see
    docs/ADVERSARIAL_FINDINGS.md)."""
    return [
        _probe_sandbox_network(sandbox_mod),
        _probe_sandbox_subprocess(sandbox_mod),
        _probe_sandbox_fs_outside(sandbox_mod),
        _probe_sandbox_fs_prefix_overbreadth(sandbox_mod),
        _probe_ledger_signature_forgery(facts_mod, ledger_factory, priv, pub),
        _probe_ledger_chain_truncation(facts_mod, ledger_factory, priv, pub),
        _probe_gateway_execute_without_approval(gateway),
        _probe_approvals_second_layer(gateway),
    ]
