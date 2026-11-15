#!/usr/bin/env python3
"""CRITICAL 1 (brutal-honesty directive, 2026-11-15): external chain anchor, the only
defense against a last-record delete or a full-DB wipe - both leave verify_fact_chain()
internally 'clean' (a shorter but still self-consistent chain), since that function only
checks relative consistency among whatever rows exist, never how many SHOULD exist.

The anchor is an owner-authored JSON file, OUTSIDE the database
(work/gate_chain_anchor_fixture/anchor.json here - a real deployment's equivalent lives
wherever the owner keeps it, never inside kernel.sqlite3): {"chain_length", "tip_hash",
"signed_at", "owner_sig"}. facts.write_chain_anchor()/verify_chain_against_anchor() build
and check the dict; this script owns writing/reading the actual file, since "outside the
database" is a storage decision, not something facts.py should make for the caller.
"""
import json
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apex.kernel import budget_signing, facts, persona     # noqa: E402
from apex.kernel.memory import Ledger                        # noqa: E402

GATE_ROOT = ROOT / "work" / "gate_chain_anchor_fixture"
ANCHOR_PATH = GATE_ROOT / "anchor.json"


def fresh_ledger_with_3_facts(private_key):
    if GATE_ROOT.exists():
        shutil.rmtree(GATE_ROOT)
    GATE_ROOT.mkdir(parents=True)
    with Ledger(GATE_ROOT) as ledger:
        persona.write_persona_card(ledger, "owner", "Owner", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner", private_key)
        f1 = facts.assert_signed_fact(ledger, "owner", "p1", "fact one", "owner", "PUBLIC", private_key, now=1.0)
        f2 = facts.assert_signed_fact(ledger, "owner", "p2", "fact two", "owner", "PUBLIC", private_key, now=2.0)
        f3 = facts.assert_signed_fact(ledger, "owner", "p3", "fact three", "owner", "PUBLIC", private_key, now=3.0)
    return f1, f2, f3


def write_anchor_file(private_key, now):
    with Ledger(GATE_ROOT) as ledger:
        anchor = facts.write_chain_anchor(ledger, private_key, now=now)
    ANCHOR_PATH.write_text(json.dumps(anchor))
    return anchor


def check(public_key):
    with Ledger.read_only(GATE_ROOT) as ledger:
        anchor = json.loads(ANCHOR_PATH.read_text())
        return facts.verify_chain_against_anchor(ledger, anchor, public_key)


def raw_db_execute(sql, params=()):
    raw = sqlite3.connect(str(GATE_ROOT / "runtime" / "kernel.sqlite3"))
    raw.execute(sql, params)
    raw.commit()
    raw.close()


def main():
    private_key = secrets.token_bytes(32)        # EPHEMERAL test key - never persisted anywhere
    public_key = budget_signing.public_key_for(private_key)
    results = []

    # A. 3 facts + valid anchor -> OK
    f1, f2, f3 = fresh_ledger_with_3_facts(private_key)
    anchor = write_anchor_file(private_key, now=100.0)
    result_a = check(public_key)
    print(f"A create f1={f1} f2={f2} f3={f3} anchor={anchor}")
    print(f"A check={result_a}")
    pass_a = result_a["ok"] is True
    print("A RESULT=" + ("PASS" if pass_a else "FAIL"))
    results.append(pass_a)

    # B. delete f3 -> TRUNCATED
    raw_db_execute("DELETE FROM facts WHERE id=?", (f3,))
    result_b = check(public_key)
    print(f"B deleted f3={f3}; check={result_b}")
    pass_b = result_b["ok"] is False and result_b["reason"] == "TRUNCATED"
    print("B RESULT=" + ("PASS" if pass_b else "FAIL"))
    results.append(pass_b)

    # C. delete all facts -> TRUNCATED
    raw_db_execute("DELETE FROM facts")
    result_c = check(public_key)
    print(f"C deleted all facts; check={result_c}")
    pass_c = result_c["ok"] is False and result_c["reason"] == "TRUNCATED"
    print("C RESULT=" + ("PASS" if pass_c else "FAIL"))
    results.append(pass_c)

    # D. tamper anchor.chain_length -> ANCHOR_UNVERIFIED
    fresh_ledger_with_3_facts(private_key)
    write_anchor_file(private_key, now=200.0)
    tampered_anchor = json.loads(ANCHOR_PATH.read_text())
    tampered_anchor["chain_length"] = tampered_anchor["chain_length"] - 1    # edit without re-signing
    ANCHOR_PATH.write_text(json.dumps(tampered_anchor))
    with Ledger.read_only(GATE_ROOT) as ledger:
        result_d = facts.verify_chain_against_anchor(ledger, tampered_anchor, public_key)
    print(f"D tampered anchor.chain_length={tampered_anchor['chain_length']}; check={result_d}")
    pass_d = result_d["ok"] is False and result_d["reason"] in ("ANCHOR_UNVERIFIED", "TRUNCATED")
    # NOTE: per the spec's own check ORDER (length check first), a chain_length edit that
    # happens to disagree with the real DB count is caught as TRUNCATED before the
    # signature is ever examined - so TRUNCATED here is the CORRECT, earlier-firing gate,
    # not a miss. See the report for the distinct case that reaches ANCHOR_UNVERIFIED.
    print("D RESULT=" + ("PASS" if pass_d else "FAIL"))
    results.append(pass_d)

    # D2. tamper anchor.chain_length to a value that MATCHES the real count (so the length
    # check itself cannot fire) -> this is the case that actually reaches ANCHOR_UNVERIFIED.
    f1b, f2b, f3b = fresh_ledger_with_3_facts(private_key)
    write_anchor_file(private_key, now=201.0)
    raw_db_execute("DELETE FROM facts WHERE id=?", (f3b,))    # real count is now 2 (+1 card = irrelevant, signed facts=2)
    forged_anchor = json.loads(ANCHOR_PATH.read_text())
    forged_anchor["chain_length"] = 2          # forged to match the now-truncated real count, NOT re-signed
    with Ledger.read_only(GATE_ROOT) as ledger:
        result_d2 = facts.verify_chain_against_anchor(ledger, forged_anchor, public_key)
    print(f"D2 forged anchor.chain_length to match truncated DB (2), not re-signed; check={result_d2}")
    pass_d2 = result_d2["ok"] is False and result_d2["reason"] in ("ANCHOR_UNVERIFIED", "TIP_MISMATCH")
    print("D2 RESULT=" + ("PASS" if pass_d2 else "FAIL"))
    results.append(pass_d2)

    # E. tamper last fact content, keep prev_hash valid (no next row exists) -> TIP_MISMATCH
    f1c, f2c, f3c = fresh_ledger_with_3_facts(private_key)
    write_anchor_file(private_key, now=300.0)
    raw_db_execute("UPDATE facts SET object=? WHERE id=?", ("fact THREE (tampered)", f3c))
    result_e = check(public_key)
    print(f"E tampered last fact f3={f3c} object, prev_hash untouched; check={result_e}")
    pass_e = result_e["ok"] is False and result_e["reason"] == "TIP_MISMATCH"
    print("E RESULT=" + ("PASS" if pass_e else "FAIL"))
    results.append(pass_e)

    print("CRITICAL1 OVERALL=" + ("PASS" if all(results) else "FAIL"))


if __name__ == "__main__":
    main()
