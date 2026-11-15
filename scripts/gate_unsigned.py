#!/usr/bin/env python3
"""CRITICAL 2 (brutal-honesty directive, 2026-11-15): an unsigned FINANCE/MEDICAL fact must
never be returned by recall_fact(), even if it somehow gets into the database (a raw SQL
insert bypassing the application layer entirely, simulating an attacker or a bug). Synthetic
fixture only - work/gate_unsigned_fixture/.
"""
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, facts, persona     # noqa: E402
from apex.kernel.memory import Ledger                        # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_unsigned_fixture"


def main():
    if GATE_ROOT.exists():
        import shutil
        shutil.rmtree(GATE_ROOT)
    GATE_ROOT.mkdir(parents=True)
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)

    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)
        persona.write_persona_card(ledger, "companion_f", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   private_key, grants=["FINANCE"])     # already granted - the attack must still fail

        # A. assert_fact(..., data_class='FINANCE') -> UnsignedFactError
        try:
            facts.assert_fact(ledger, "persona:owner", "memory_shared", "F_fin unsigned attempt", "owner",
                              data_class="FINANCE")
            case_a = "DID_NOT_RAISE"
        except facts.UnsignedFactError as exc:
            case_a = f"RAISED:{type(exc).__name__}:{exc}"
        print(f"A assert_fact(data_class=FINANCE) -> {case_a}")
        pass_a = case_a.startswith("RAISED:UnsignedFactError")
        print("A RESULT=" + ("PASS" if pass_a else "FAIL"))

        # B. Directly INSERT a fact (owner_sig=NULL, data_class=FINANCE, shared=TRUE) into DB,
        # bypassing assert_fact()/assert_signed_fact() entirely - simulating an attacker with
        # raw DB write access, or a latent bug elsewhere that produced an unsigned row anyway.
        cur = ledger.db.execute(
            "INSERT INTO facts (subject, predicate, object, source, asserted_at, owner_sig, prev_hash, data_class) "
            "VALUES (?,?,?,?,?,NULL,NULL,?)",
            ("persona:owner", "memory_shared", "F_fin injected via raw SQL", "attacker", 1.0, "FINANCE"))
        ledger.db.commit()
        injected_fact_id = cur.lastrowid
        print(f"B raw-SQL-injected fact_id={injected_fact_id} owner_sig=NULL data_class=FINANCE shared=True")
        row_check = ledger.db.execute("SELECT owner_sig FROM facts WHERE id=?", (injected_fact_id,)).fetchone()
        print(f"B confirmed owner_sig in DB = {row_check[0]!r}")

        # C. companion_f (grants=['FINANCE']) .recall_fact(injected_fact_id) -> UNVERIFIED_FACT
        try:
            leaked = persona.recall_fact(ledger, "companion_f", injected_fact_id, public_key)
            print(f"C did NOT raise - leaked: {leaked}")
            pass_c = False
        except persona.PersonaIsolationError as exc:
            print(f"C raised PersonaIsolationError: {exc}")
            pass_c = "UNVERIFIED_FACT" in str(exc)
        print("C RESULT=" + ("PASS" if pass_c else "FAIL"))

        print("CRITICAL2 OVERALL=" + ("PASS" if (pass_a and pass_c) else "FAIL"))


if __name__ == "__main__":
    main()
