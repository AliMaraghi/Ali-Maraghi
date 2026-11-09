"""Produce all three offline domain outputs from the committed example inputs."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from apex.domains import Interval, OpportunityScenario, PersonalTask, Shot, MediaAsset
from apex.domains import evaluate_opportunity, plan_day, build_production_manifest
from apex.kernel.evidence import read_local
from apex.kernel.schema import strict_json


def run(domain):
    filenames = {"opportunity": "opportunity_synthetic.json", "personal": "personal_synthetic.json", "studio": "invisible_systems_75s.json"}
    doc = strict_json(read_local(ROOT, "examples/" + filenames[domain], 262144).decode())
    if domain == "opportunity":
        values = dict(doc["scenario"])
        for key in ("success_probability", "revenue_if_success_gbp", "cash_cost_gbp", "hours_required", "hourly_time_value_gbp"):
            values[key] = Interval(**values[key])
        for key in ("assumptions", "evidence_refs"):
            values[key] = tuple(values[key])
        return evaluate_opportunity(OpportunityScenario(**values))
    if domain == "personal":
        return plan_day([PersonalTask(**x) for x in doc["tasks"]], doc["available_minutes"], low_energy=doc["low_energy"])
    return build_production_manifest([Shot(**x) for x in doc["shots"]], [MediaAsset(**x) for x in doc["assets"]], workspace=ROOT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", choices=["opportunity", "personal", "studio", "all"])
    args = parser.parse_args()
    selected = ["opportunity", "personal", "studio"] if args.domain == "all" else [args.domain]
    print(json.dumps({domain: run(domain) for domain in selected}, indent=2, ensure_ascii=True))
