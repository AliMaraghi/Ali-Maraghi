#!/usr/bin/env python3
"""GAP 3 (brutal-honesty directive, 2026-11-15): chain verification must check owner_sig
per record, not just prev_hash. Two scenarios, two fresh fixtures, synthetic only.

Scenario A proves the signature check adds real value beyond the hash chain alone: tamper
record 2's content, then ALSO recompute record 3's prev_hash from the tampered content (so
a prev_hash-only check walking that far would see nothing wrong) - verify_fact_chain() must
still stop at record 2 with SIGNATURE_INVALID, because record 2's own signature was computed
over its ORIGINAL content and cannot be forged to match the tamper without the private key.

Scenario B proves the hash-chain check still works: delete record 2 entirely (no signature
exists to check against something that isn't there) - verify_fact_chain() must report
record 3's prev_hash no longer matching, PREV_HASH_MISMATCH.
"""
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, facts, persona     # noqa: E402
from apex.kernel.memory import Ledger                        # noqa: E402

A_ROOT = ROOT / "work" / "gate_chain_sig_a"
B_ROOT = ROOT / "work" / "gate_chain_sig_b"


def scenario_a():
    if A_ROOT.exists():
        shutil.rmtree(A_ROOT)
    A_ROOT.mkdir(parents=True)
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted
    public_key = budget_signing.public_key_for(private_key)
    with Ledger(A_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner")
        f1 = facts.assert_signed_fact(ledger, "owner", "p1", "fact one", "owner", "PUBLIC", private_key, now=1.0)
        f2 = facts.assert_signed_fact(ledger, "owner", "p2", "fact two", "owner", "PUBLIC", private_key, now=2.0)
        f3 = facts.assert_signed_fact(ledger, "owner", "p3", "fact three", "owner", "PUBLIC", private_key, now=3.0)
        clean = facts.verify_fact_chain(ledger, public_key)
    print(f"SCENARIO_A create f1={f1} f2={f2} f3={f3} clean_chain={clean}")

    db_path = A_ROOT / "runtime" / "kernel.sqlite3"
    raw = sqlite3.connect(str(db_path))
    tampered_object = "fact TWO (tampered)"
    raw.execute("UPDATE facts SET object=? WHERE id=?", (tampered_object, f2))
    # Recompute record 3's prev_hash from record 2's NEW (tampered) content, so a
    # prev_hash-only check walking that far would see record 3 as consistent too.
    row2 = raw.execute(
        "SELECT id, subject, predicate, object, source, asserted_at, prev_hash, data_class "
        "FROM facts WHERE id=?", (f2,)).fetchone()
    recomputed_prev_hash_for_f3 = facts._chain_value(*row2)
    raw.execute("UPDATE facts SET prev_hash=? WHERE id=?", (recomputed_prev_hash_for_f3, f3))
    raw.commit()
    raw.close()
    print(f"SCENARIO_A tampered f2 object -> {tampered_object!r}; recomputed f3.prev_hash to match")

    with Ledger.read_only(A_ROOT) as ledger:
        result = facts.verify_fact_chain(ledger, public_key)
    print(f"SCENARIO_A chain_after_tamper={result}")
    passed = result["ok"] is False and result["first_broken_id"] == f2 and result["reason"] == "SIGNATURE_INVALID"
    print("SCENARIO_A RESULT=" + ("PASS" if passed else "FAIL"))
    return passed


def scenario_b():
    if B_ROOT.exists():
        shutil.rmtree(B_ROOT)
    B_ROOT.mkdir(parents=True)
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted
    public_key = budget_signing.public_key_for(private_key)
    with Ledger(B_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner")
        f1 = facts.assert_signed_fact(ledger, "owner", "p1", "fact one", "owner", "PUBLIC", private_key, now=1.0)
        f2 = facts.assert_signed_fact(ledger, "owner", "p2", "fact two", "owner", "PUBLIC", private_key, now=2.0)
        f3 = facts.assert_signed_fact(ledger, "owner", "p3", "fact three", "owner", "PUBLIC", private_key, now=3.0)
        clean = facts.verify_fact_chain(ledger, public_key)
    print(f"SCENARIO_B create f1={f1} f2={f2} f3={f3} clean_chain={clean}")

    db_path = B_ROOT / "runtime" / "kernel.sqlite3"
    raw = sqlite3.connect(str(db_path))
    raw.execute("DELETE FROM facts WHERE id=?", (f2,))
    raw.commit()
    raw.close()
    print(f"SCENARIO_B deleted f2={f2}")

    with Ledger.read_only(B_ROOT) as ledger:
        result = facts.verify_fact_chain(ledger, public_key)
    print(f"SCENARIO_B chain_after_delete={result}")
    passed = result["ok"] is False and result["first_broken_id"] == f3 and result["reason"] == "PREV_HASH_MISMATCH"
    print("SCENARIO_B RESULT=" + ("PASS" if passed else "FAIL"))
    return passed


if __name__ == "__main__":
    a_ok = scenario_a()
    b_ok = scenario_b()
    print("GAP3 OVERALL=" + ("PASS" if (a_ok and b_ok) else "FAIL"))
