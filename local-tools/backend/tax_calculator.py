"""Deterministic UK ESPP/income-tax/NIC calculator - pure integer arithmetic, no LLM call,
no network. Every number traces back to a value you supply (your own espp inputs) or a UK tax
rules file you provide and attest the source/verification date of. Nothing here is tax advice;
it is arithmetic against numbers and rules you give it. Extracted unchanged from the parent
project's A-8 (FinancialIntelligence) generator - the planner/evaluator harness around it was
part of the removed "theater"; this is the actual calculation, kept as-is.
"""
from __future__ import annotations


class TaxCalculatorError(ValueError):
    pass


def income_tax(income: int, rules: dict) -> int:
    tax_rules = rules["income_tax"]
    taxable, prev, tax = max(0, income - tax_rules["personal_allowance_pence"]), 0, 0
    for band in tax_rules["bands"]:
        upto = band["upto_pence"] if band["upto_pence"] is not None else taxable
        part = max(0, min(taxable, upto) - prev)
        tax += part * band["rate_bp"] // 10000
        prev = max(prev, upto)
    return tax


def employee_nic(income: int, rules: dict):
    nic = rules.get("nic")
    if not nic:
        return None
    main = max(0, min(income, nic["upper_limit_pence"]) - nic["primary_threshold_pence"])
    upper = max(0, income - nic["upper_limit_pence"])
    return main * nic["main_rate_bp"] // 10000 + upper * nic["upper_rate_bp"] // 10000


def calculate(data: dict, rules: dict) -> dict:
    """`data`: {"annual_salary_pence": int, "espp": {"contribution_pence", "fmv_start_pence_per_share",
    "fmv_end_pence_per_share", "discount_bp"}} (all non-negative integers).
    `rules`: {"tax_year", "source", "verified_on", "income_tax": {...}, "nic": {...} (optional)}."""
    if not all(isinstance(rules.get(k), str) and rules[k] for k in ("tax_year", "source", "verified_on")):
        raise TaxCalculatorError("Rules file needs tax_year, source and verified_on")
    try:
        salary, espp = data["annual_salary_pence"], data["espp"]
        values = (salary, espp["contribution_pence"], espp["fmv_start_pence_per_share"],
                  espp["fmv_end_pence_per_share"], espp["discount_bp"])
    except KeyError as exc:
        raise TaxCalculatorError(f"Missing required field: {exc}") from None
    for value in values:
        if type(value) is not int or value < 0:
            raise TaxCalculatorError("Inputs must be non-negative integers in pence / basis points")

    price = min(espp["fmv_start_pence_per_share"], espp["fmv_end_pence_per_share"]) * (10000 - espp["discount_bp"]) // 10000
    if price <= 0:
        raise TaxCalculatorError("Purchase price must be positive")
    shares = espp["contribution_pence"] // price
    gain = shares * (espp["fmv_end_pence_per_share"] - price)
    tax_extra = income_tax(salary + gain, rules) - income_tax(salary, rules)
    nic_now, nic_after = employee_nic(salary, rules), employee_nic(salary + gain, rules)
    nic_extra = 0 if nic_now is None else nic_after - nic_now
    net = gain - tax_extra - nic_extra
    action = "exercise_espp_now" if net > 0 else "hold_espp_do_not_exercise"

    return {
        "action": action, "shares": shares, "gain_pence": gain, "extra_income_tax_pence": tax_extra,
        "extra_employee_nic_pence": nic_extra if nic_now is not None else None,
        "net_pence": net, "nic_modelled": nic_now is not None,
        "summary": (f"{shares} whole shares, gain {gain}p, extra income tax {tax_extra}p, "
                    f"extra employee NIC {'not modelled' if nic_now is None else str(nic_extra) + 'p'}, "
                    f"net {net}p ({rules['tax_year']} rules, source {rules['source']}, "
                    f"verified {rules['verified_on']}). One-click action: {action}."),
        "disclaimer": "Decision support only, not tax advice. Personal-allowance taper, student "
                       "loan, pension relief, capital gains and Universal Credit effects are not "
                       "modelled. Assumes the ESPP gain is taxed as employment income - the real "
                       "treatment depends on your specific plan and is not determined here.",
    }
