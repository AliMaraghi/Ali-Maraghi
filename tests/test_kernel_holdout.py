"""Frozen synthetic policy cases are regression cases after their first run."""
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from datetime import datetime, timezone
from test_kernel import document
from apex.kernel.schema import Case
from apex.kernel.engine import evaluate

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kernel_benchmark", ROOT / "scripts/benchmark_kernel.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class FrozenPolicyTests(unittest.TestCase):
    def test_frozen_policy_decisions_and_measured_baseline(self):
        result = benchmark.benchmark()
        for case in result["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["candidate"], case["expected"])
        self.assertEqual(result["real_world_superiority"], "NOT_TESTED")
        self.assertFalse(result["candidate_promoted"])
        self.assertEqual(result["receipt"]["safety_regressions"], 0)

    def test_frozen_synthetic_evidence_cases(self):
        data = json.loads((ROOT / "reports/validation/kernel_holdout_cases.json").read_text())
        for row in data["evidence_cases"]:
            with self.subTest(case=row["id"]), tempfile.TemporaryDirectory(dir=ROOT / "work") as tmp:
                root = Path(tmp)
                case = document(root)
                source = case["evidence"][0]
                # These are artificial claims regardless of their test metadata.
                source.update(synthetic=False, sensitivity="public")
                mutation = row["mutation"]
                if mutation == "add_refutation":
                    source["stance"] = "refutes"
                elif mutation == "future_retrieval":
                    source["retrieved_at"] = "2027-01-01T00:00:00Z"
                elif mutation == "cross_domain":
                    source["domain"] = "studio"
                elif mutation == "model_output":
                    source["method"] = "model_output"
                elif mutation == "duplicate_source":
                    case["claims"][0]["kind"] = "inference"
                    case["claims"][0]["evidence_ids"].append("copy")
                    case["evidence"].append(dict(source, id="copy", independence_group="relabeled"))
                elif mutation == "fabricated_excerpt":
                    source["excerpt"] = "This text is not present in the artifact."
                elif mutation == "changed_content":
                    (root / "source.txt").write_text("replacement")
                elif mutation == "unknown_reference":
                    case["claims"][0]["evidence_ids"] = ["missing"]
                else:
                    self.fail("Unimplemented frozen case")
                result = evaluate(Case.parse(case), root, datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
                self.assertIn(row["expected_issue"], {f["code"] for f in result["critic"]["findings"]})
                self.assertFalse(result["empirical_superiority_proven"])


if __name__ == "__main__":
    unittest.main()
