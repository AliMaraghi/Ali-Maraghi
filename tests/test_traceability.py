"""Source loss/tampering and false completion must fail the traceability gate."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apex_traceability", ROOT / "scripts/traceability.py")
trace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace)


class TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / trace.REGISTRY).read_text(encoding="utf-8"))

    def test_immutable_sources_and_every_nonblank_line_are_retained(self):
        self.assertEqual(trace.validate(self.registry), [])
        actual = {(row["source_anchor"]["path"], row["source_anchor"]["start_line"])
                  for row in self.registry["source_units"]}
        expected = set()
        for name, _ in trace.SOURCES.values():
            path = trace.HANDOFF + name
            for n, line in enumerate((ROOT / path).read_bytes().splitlines(), 1):
                if line.strip():
                    expected.add((path, n))
        self.assertEqual(actual, expected)

    def test_all_sections_roles_social_clauses_appendices_and_gates_have_entries(self):
        ids = {row["requirement_id"] for row in self.registry["requirements"]}
        required = {f"S{i:02}" for i in range(19)}
        required |= {f"CLAUSE-8-{i}" for i in range(1, 19)}
        required |= {f"CLAUSE-6-1-{i}" for i in range(1, 21)}
        required |= {"APP-" + key for key in ("HEALTH", "KERNEL", "PWA", "ML", "ORIGINALITY", "PRESERVATION", "ACCEPTANCE", "BLOCKERS", "SIGNATURE", "ARCHIVE", "ARCHIVED-GATE")}
        required |= {f"A{i:02}" for i in range(1, 10)} | {f"G{i}" for i in range(8)}
        required |= {f"HISTORICAL-12-{i}" for i in range(1, 11)} | {f"HISTORICAL-18-{i}" for i in range(3, 7)}
        self.assertTrue(required <= ids)

    def test_dropping_one_source_line_fails(self):
        data = copy.deepcopy(self.registry)
        data["source_units"].pop()
        self.assertTrue(trace.validate(data))

    def test_dropping_role_or_appendix_fails(self):
        for rid in ("CLAUSE-8-11", "APP-HEALTH", "CLAUSE-6-1-20", "HISTORICAL-12-3"):
            data = copy.deepcopy(self.registry)
            data["requirements"] = [row for row in data["requirements"] if row["requirement_id"] != rid]
            self.assertTrue(trace.validate(data), rid)

    def test_retargeting_source_anchor_fails(self):
        data = copy.deepcopy(self.registry)
        data["requirements"][0]["source_anchor"]["start_line"] += 1
        self.assertTrue(trace.validate(data))

    def test_forged_source_line_hash_fails(self):
        data = copy.deepcopy(self.registry)
        data["source_units"][0]["source_anchor"]["sha256"] = "0" * 64
        self.assertTrue(trace.validate(data))

    def test_unsupported_completion_and_deployment_fail(self):
        for field, value in (("acceptance_status", "PASS"), ("implementation_status", "DEPLOYED"), ("acceptance_status", "COMPLETE")):
            data = copy.deepcopy(self.registry)
            data["requirements"][0][field] = value
            self.assertTrue(trace.validate(data))

    def test_duplicate_requirement_id_fails(self):
        data = copy.deepcopy(self.registry)
        data["requirements"].append(copy.deepcopy(data["requirements"][0]))
        self.assertTrue(trace.validate(data))

    def test_mapped_paths_cannot_escape_workspace(self):
        for path in ("/etc/passwd", "../outside.py", ""):
            data = copy.deepcopy(self.registry)
            data["requirements"][0]["implementation"] = [{"path": path, "relationship": "implemented"}]
            self.assertTrue(trace.validate(data))

    def test_missing_implemented_file_is_not_accepted_as_evidence(self):
        data = copy.deepcopy(self.registry)
        data["requirements"][0]["implementation"] = [{"path": "core/apex/nonexistent.py", "relationship": "implemented"}]
        self.assertTrue(trace.validate(data))

    def test_actual_source_mutation_fails_without_changing_original(self):
        (ROOT / "work").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="traceability-test-", dir=ROOT / "work") as temp:
            target = Path(temp)
            for name, _ in trace.SOURCES.values():
                destination = target / trace.HANDOFF / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / trace.HANDOFF / name, destination)
            source = target / trace.HANDOFF / trace.SOURCES["M"][0]
            source.write_bytes(source.read_bytes() + b"\nunauthorized modification\n")
            errors = trace.validate(self.registry, target)
            self.assertTrue(any("digest mismatch" in message for message in errors))
        self.assertEqual(trace.validate(self.registry), [])

    def test_registry_does_not_duplicate_private_source_text(self):
        text = json.dumps(self.registry, ensure_ascii=False)
        self.assertTrue(text.isascii())
        self.assertNotIn("source_text", text)

    def test_source_gap_cannot_be_erased(self):
        data = copy.deepcopy(self.registry)
        row = next(r for r in data["requirements"] if r["requirement_id"] == "HISTORICAL-12-1")
        row["source_gap"] = None
        self.assertTrue(trace.validate(data))

    def test_tested_status_requires_evidence(self):
        data = copy.deepcopy(self.registry)
        data["requirements"][0].update(implementation_status="TESTED", test=[], evidence=[])
        self.assertTrue(trace.validate(data))


if __name__ == "__main__":
    unittest.main()
