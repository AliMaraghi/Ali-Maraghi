#!/usr/bin/env python3
"""Phase 2 gate: cross-process signed-fact recall + tamper detection (brutal-honesty
directive, 2026-11-15). Synthetic fixture only - work/gate_phase2_fixture/, never
runtime/inbox or runtime/rules.

AMENDMENT 2: this script generates an EPHEMERAL test key with secrets.token_bytes(32) at
process start (in --step1 only), uses it to sign exactly once, and never writes it to disk,
logs it, or reads a real key from anywhere. Only the derived PUBLIC key (not sensitive) is
written to a local scratch file so the separate --step2/--tamper process invocations can
verify without ever needing the private key. The real owner key, if this is ever wired into
a real deployment, lives only on the personal machine and is never generated, read, or
written by this work account.

Usage (three SEPARATE process invocations, per the gate's own spec):
  python3 -B scripts/gate_phase2.py --step1
  python3 -B scripts/gate_phase2.py --step2
  python3 -B scripts/gate_phase2.py --tamper
"""
import argparse
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, facts, persona     # noqa: E402
from apex.kernel.memory import Ledger                        # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_phase2_fixture"
PUBKEY_FILE = GATE_ROOT / "owner_pubkey.hex"
FACT_ID_FILE = GATE_ROOT / "fact_id.txt"


def step1():
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    private_key = secrets.token_bytes(32)          # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)
        fact_id = facts.assert_signed_fact(ledger, "owner", "preference", "prefers British English",
                                           "owner", "PUBLIC", private_key, now=1000.0)
    PUBKEY_FILE.write_text(public_key.hex())
    FACT_ID_FILE.write_text(str(fact_id))
    print(f"STEP1 fact_id={fact_id} public_key_hex={public_key.hex()}")
    print("STEP1 private_key_bytes_written_to_disk=False private_key_logged=False")
    # private_key goes out of scope at the end of this function and is never persisted.


def step2():
    public_key = bytes.fromhex(PUBKEY_FILE.read_text())
    fact_id = int(FACT_ID_FILE.read_text())
    with Ledger.read_only(GATE_ROOT) as ledger:
        row = facts.query_fact(ledger, "owner", "preference")
        content_matches = row is not None and row["id"] == fact_id and row["object"] == "prefers British English"
        signature_verifies = facts.verify_fact_signature(ledger, fact_id, public_key)
    print(f"STEP2 fact_id={fact_id} content={row['object'] if row else None} content_matches={content_matches} "
          f"signature_verifies={signature_verifies}")
    print("STEP2 RESULT=" + ("PASS" if (content_matches and signature_verifies) else "FAIL"))


def tamper():
    public_key = bytes.fromhex(PUBKEY_FILE.read_text())
    fact_id = int(FACT_ID_FILE.read_text())
    db_path = GATE_ROOT / "runtime" / "kernel.sqlite3"
    raw = sqlite3.connect(str(db_path))
    before = raw.execute("SELECT object FROM facts WHERE id=?", (fact_id,)).fetchone()[0]
    tampered = before[:-1] + ("x" if before[-1] != "x" else "y")     # flip exactly the last byte
    raw.execute("UPDATE facts SET object=? WHERE id=?", (tampered, fact_id))
    raw.commit()
    raw.close()
    with Ledger.read_only(GATE_ROOT) as ledger:
        signature_verifies_after_tamper = facts.verify_fact_signature(ledger, fact_id, public_key)
    print(f"TAMPER fact_id={fact_id} before={before!r} after={tampered!r}")
    print(f"TAMPER signature_verifies_after_tamper={signature_verifies_after_tamper}")
    print("TAMPER RESULT=" + ("PASS" if signature_verifies_after_tamper is False else "FAIL"))


def chain_test():
    """STEP 4's second half: with prev_hash active on every row, delete one row entirely
    (not just edit it) and confirm verify_fact_chain() detects it and reports the first
    broken id - not a boolean. Runs in its own fixture dir so it never touches the
    already-tampered F1 row from --tamper above."""
    chain_root = GATE_ROOT.parent / "gate_phase2_chain_fixture"
    import shutil
    if chain_root.exists():
        shutil.rmtree(chain_root)
    chain_root.mkdir(parents=True)
    from apex.kernel import facts
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted anywhere
    with Ledger(chain_root) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   private_key)
        f1 = facts.assert_signed_fact(ledger, "owner", "preference_1", "likes tea", "owner", "PUBLIC", private_key, now=1.0)
        f2 = facts.assert_signed_fact(ledger, "owner", "preference_2", "likes rain", "owner", "PUBLIC", private_key, now=2.0)
        public_key = budget_signing.public_key_for(private_key)
        clean = facts.verify_fact_chain(ledger, public_key)
    print(f"CHAINTEST before_delete f1={f1} f2={f2} chain={clean}")
    print("CHAINTEST clean_chain_ok=" + str(clean["ok"]))

    db_path = chain_root / "runtime" / "kernel.sqlite3"
    raw = sqlite3.connect(str(db_path))
    raw.execute("DELETE FROM facts WHERE id=?", (f1,))
    raw.commit()
    raw.close()

    with Ledger.read_only(chain_root) as ledger:
        broken = facts.verify_fact_chain(ledger, public_key)
    print(f"CHAINTEST after_delete_f1 chain={broken}")
    detected = (not broken["ok"]) and broken["first_broken_id"] == f2
    print(f"CHAINTEST deletion_detected={not broken['ok']} first_broken_id={broken['first_broken_id']} expected={f2}")
    print("CHAINTEST RESULT=" + ("PASS" if detected else "FAIL"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step1", action="store_true")
    parser.add_argument("--step2", action="store_true")
    parser.add_argument("--tamper", action="store_true")
    parser.add_argument("--chain-test", action="store_true")
    args = parser.parse_args()
    if args.step1:
        step1()
    elif args.step2:
        step2()
    elif args.tamper:
        tamper()
    elif args.chain_test:
        chain_test()
    else:
        sys.exit("pass --step1, --step2, --tamper or --chain-test")
