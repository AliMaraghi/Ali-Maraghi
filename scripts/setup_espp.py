#!/usr/bin/env python3
"""One-time local setup: writes YOUR real salary/ESPP numbers into the already-gitignored
runtime/inbox/espp_inputs.json, in the exact shape core/apex/agents_impl.py's real A-8
(FinancialIntelligence) already reads - no new agent file needed, that logic already exists and
is tested (see income_tax()/employee_nic()/FinancialIntelligence.run() in agents_impl.py).

Nothing here is committed to git: runtime/ is already ignored (see .gitignore / AGENTS.md's
"Keep runtime journals and scratch files ignored"). Numbers are read from command-line flags you
type directly in your own terminal, never pasted into this chat, and never printed back except in
the confirmation summary below (pence/percent only, which you already typed).

Usage (amounts in whole pounds, discount as a percent):
  python3 scripts/setup_espp.py \\
      --gross-salary 42000 \\
      --contribution 1500 \\
      --fmv-start 25.00 --fmv-end 31.00 \\
      --discount-percent 15

This does NOT write runtime/rules/uk_tax_rules.json by default - that file needs the actual
current UK income-tax/NIC/UC/mortgage figures from a real, dated source (e.g. gov.uk,
bankofengland.co.uk), which this script does not invent or guess. Pass --rules-source and
--rules-verified-on plus whichever section's flags you want (--band for income tax,
--uc-capital-* for Universal Credit, --mortgage-income-multiplier for the LTI reference) to add
or update that section - runs are additive, so you can set up income tax first and add UC later
without resupplying the tax bands.

Example adding the Universal Credit capital-tariff section to an existing rules file:
  python3 scripts/setup_espp.py --gross-salary 42000 --contribution 1500 --fmv-start 25.00 \\
      --fmv-end 31.00 --discount-percent 15 --capital 8000 \\
      --rules-source "https://www.gov.uk/universal-credit/how-your-earnings-affect-your-payments" \\
      --rules-verified-on 2026-11-13 \\
      --uc-capital-lower 6000 --uc-capital-upper 16000 --uc-capital-tariff-unit 250 --uc-capital-tariff-deduction 4.35
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def to_pence(pounds: float) -> int:
    return round(pounds * 100)


def to_bp(percent: float) -> int:
    return round(percent * 100)


def write_espp_inputs(args) -> Path:
    path = ROOT / "runtime" / "inbox" / "espp_inputs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "annual_salary_pence": to_pence(args.gross_salary),
        "espp": {
            "contribution_pence": to_pence(args.contribution),
            "fmv_start_pence_per_share": to_pence(args.fmv_start),
            "fmv_end_pence_per_share": to_pence(args.fmv_end),
            "discount_bp": to_bp(args.discount_percent),
        },
    }
    if args.capital is not None:
        data["capital_pence"] = to_pence(args.capital)  # optional - triggers the UC calculation
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)
    return path


def write_tax_rules(args) -> Path | None:
    writing_anything = args.bands or args.uc_capital_lower is not None or args.mortgage_income_multiplier is not None
    if not writing_anything:
        return None
    path = ROOT / "runtime" / "rules" / "uk_tax_rules.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Merge into whatever's already there (e.g. income_tax bands set up in an earlier run) rather
    # than overwrite it - this script is meant to be run incrementally, section by section.
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data["source"], data["verified_on"] = args.rules_source, args.rules_verified_on
    if args.tax_year is not None:
        data["tax_year"] = args.tax_year
    if args.bands:
        bands = []
        for spec in args.bands:
            upto, rate = spec.split(":")
            bands.append({"upto_pence": None if upto == "none" else to_pence(float(upto)),
                          "rate_bp": to_bp(float(rate))})
        data["income_tax"] = {"personal_allowance_pence": to_pence(args.personal_allowance), "bands": bands}
    if args.nic_primary_threshold is not None:
        data["nic"] = {
            "primary_threshold_pence": to_pence(args.nic_primary_threshold),
            "upper_limit_pence": to_pence(args.nic_upper_limit),
            "main_rate_bp": to_bp(args.nic_main_rate_percent),
            "upper_rate_bp": to_bp(args.nic_upper_rate_percent),
        }
    if args.uc_capital_lower is not None:
        # Structure is stable UK welfare law (apex.agents_impl.uc_capital_deduction); these
        # threshold/deduction FIGURES still need a real, dated gov.uk source like everything else
        # in this file - verify at https://www.gov.uk/universal-credit/how-your-earnings-affect-your-payments
        # (or the current capital rules page) before setting --rules-verified-on.
        data["universal_credit"] = {
            "capital_lower_threshold_pence": to_pence(args.uc_capital_lower),
            "capital_upper_threshold_pence": to_pence(args.uc_capital_upper),
            "capital_tariff_pence": to_pence(args.uc_capital_tariff_unit),
            "capital_tariff_deduction_pence": to_pence(args.uc_capital_tariff_deduction),
        }
    if args.mortgage_income_multiplier is not None:
        # Also needs a real source - this is the FCA/PRA regulatory LTI ceiling, not a lender
        # offer; verify at bankofengland.co.uk/prudential-regulation or fca.org.uk before setting
        # --rules-verified-on. NOT to_bp(): this is a ratio (e.g. 4.5x), not a percentage -
        # mortgage_affordability_indicator() does income_pence * multiplier_bp // 10000.
        data["mortgage"] = {"income_multiplier_bp": round(args.mortgage_income_multiplier * 10000)}
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gross-salary", type=float, required=True, help="Annual gross salary in GBP")
    parser.add_argument("--contribution", type=float, required=True, help="ESPP contribution in GBP")
    parser.add_argument("--fmv-start", type=float, required=True, help="Fair market value per share at offering start, GBP")
    parser.add_argument("--fmv-end", type=float, required=True, help="Fair market value per share at purchase date, GBP")
    parser.add_argument("--discount-percent", type=float, required=True, help="ESPP discount, e.g. 15 for 15%%")

    parser.add_argument("--tax-year", default=None)
    parser.add_argument("--rules-source", default=None, help="e.g. a gov.uk URL, required if --band is used")
    parser.add_argument("--rules-verified-on", default=None, help="YYYY-MM-DD you checked that source")
    parser.add_argument("--personal-allowance", type=float, default=None, help="GBP")
    parser.add_argument("--band", action="append", default=[], metavar="UPTO:RATE_PERCENT",
                         help='Repeatable, in order, e.g. --band 50270:20 --band 125140:40 --band none:45')
    parser.add_argument("--nic-primary-threshold", type=float, default=None, help="GBP, omit to skip NIC entirely")
    parser.add_argument("--nic-upper-limit", type=float, default=None)
    parser.add_argument("--nic-main-rate-percent", type=float, default=None)
    parser.add_argument("--nic-upper-rate-percent", type=float, default=None)

    parser.add_argument("--capital", type=float, default=None, help="GBP, your current savings/capital - triggers the Universal Credit calculation")
    parser.add_argument("--uc-capital-lower", type=float, default=None, help="GBP, UC capital disregard threshold (needs --rules-source/--rules-verified-on)")
    parser.add_argument("--uc-capital-upper", type=float, default=None, help="GBP, UC capital eligibility ceiling")
    parser.add_argument("--uc-capital-tariff-unit", type=float, default=None, help="GBP, the deduction is charged per this many pounds of excess capital")
    parser.add_argument("--uc-capital-tariff-deduction", type=float, default=None, help="GBP deducted per tariff unit, per month")
    parser.add_argument("--mortgage-income-multiplier", type=float, default=None, help="e.g. 4.5 for the FCA/PRA loan-to-income ceiling (needs --rules-source/--rules-verified-on)")
    args = parser.parse_args()

    args.bands = args.band
    if args.bands or args.uc_capital_lower is not None or args.mortgage_income_multiplier is not None:
        for required in ("rules_source", "rules_verified_on"):
            if getattr(args, required) is None:
                sys.exit(f"--rules-source/--rules-verified-on are required when writing any rules section")
    if args.bands and args.personal_allowance is None:
        sys.exit("--band given but --personal-allowance is missing")
    if args.bands and args.tax_year is None:
        sys.exit("--band given but --tax-year is missing")
    if args.uc_capital_lower is not None and None in (args.uc_capital_upper, args.uc_capital_tariff_unit, args.uc_capital_tariff_deduction):
        sys.exit("--uc-capital-lower given but --uc-capital-upper/--uc-capital-tariff-unit/--uc-capital-tariff-deduction are missing")

    espp_path = write_espp_inputs(args)
    print(f"Wrote {espp_path} (mode 600) - annual_salary_pence={to_pence(args.gross_salary)}, "
          f"contribution_pence={to_pence(args.contribution)}, discount_bp={to_bp(args.discount_percent)}")
    rules_path = write_tax_rules(args)
    if rules_path:
        sections = ([f"{len(args.bands)} income-tax band(s)"] if args.bands else []) \
            + (["universal_credit"] if args.uc_capital_lower is not None else []) \
            + (["mortgage"] if args.mortgage_income_multiplier is not None else [])
        print(f"Wrote/updated {rules_path} (mode 600) - set: {', '.join(sections)}; "
              f"source={args.rules_source!r}, verified_on={args.rules_verified_on}")
    else:
        print("Did not write runtime/rules/uk_tax_rules.json - pass --band and/or --uc-capital-* and/or "
              "--mortgage-income-multiplier (with --rules-source/--rules-verified-on) to write any section.")


if __name__ == "__main__":
    main()
