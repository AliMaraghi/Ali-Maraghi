"""Offline tests: Constitutional Critic, evolution guard, evaluator, promotion gate and sub-cap."""
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apex import agent_loop, persona_twin
from apex.evolution import bootstrap, config, evaluator, guard, mutate, promote_gate
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget, BudgetDenied
from apex.kernel.memory import Ledger

STYLE = """## Tone
- direct
## Never say
- circle back
## Vocabulary
- plain words
## Humour
- dry
## Hard red lines
- Acme Widgets
- (placeholder line that must be ignored)
## Spelling
British
## Samples
""" + "\n\n".join(["I went to the market and bought far too much fruit. It was raining. Nobody minded at all."] * 6)
BASE = evaluator.BASELINE.read_text(encoding="utf-8")


def mutated(old: str, new: str) -> str:
    assert old in BASE
    return BASE.replace(old, new)


class CriticTests(unittest.TestCase):
    def setUp(self):
        self.profile = persona_twin.parse_profile(STYLE)

    def test_clean_draft_passes(self):
        self.assertEqual(persona_twin.review("I tried the new cafe on Friday. The coffee was decent. I would go back.", self.profile).status, "PASS")

    def test_tropes_spelling_and_banned_phrase_need_rewrite(self):
        verdict = persona_twin.review("Let's delve into my favorite color. We should circle back soon.", self.profile)
        self.assertEqual(verdict.status, "REWRITE")
        self.assertEqual({f.rule for f in verdict.findings}, {"ai-trope", "american-spelling", "owner-banned-phrase"})

    def test_disclosure_and_account_numbers_block(self):
        self.assertEqual(persona_twin.review("Big week at acme widgets for me.", self.profile).status, "BLOCK")
        self.assertEqual(persona_twin.review("Pay me on 00-00-00 please.", self.profile).status, "BLOCK")
        with self.assertRaises(persona_twin.CriticRejected):
            persona_twin.gate("Big week at Acme Widgets.", self.profile)

    def test_block_is_never_sent_for_redraft(self):
        calls = []
        text, verdict, rounds = persona_twin.rewrite_until_pass("News from Acme Widgets.", self.profile, lambda t, b: calls.append(b) or t)
        self.assertEqual((verdict.status, rounds, calls), ("BLOCK", 0, []))

    def test_redraft_loop_is_bounded_and_rechecked(self):
        text, verdict, rounds = persona_twin.rewrite_until_pass(
            "Let's delve into it.", self.profile, lambda t, brief: "I looked into it properly. It took a while.")
        self.assertEqual((verdict.status, rounds), ("PASS", 1))
        _, verdict, rounds = persona_twin.rewrite_until_pass("Let's delve in.", self.profile, lambda t, b: "Still delving here.")
        self.assertEqual((verdict.status, rounds), ("REWRITE", 2))

    def test_restricted_dossier_tiers_and_platform_rules_block(self):
        clean = "I fixed my bike today. It rides well."
        for tag in ("dossier_2", "dossier_3", "dossier_4", "finance", "medical", "employer"):
            self.assertEqual(persona_twin.review(clean, self.profile, input_classes=(tag,)).status, "BLOCK", tag)
        self.assertEqual(persona_twin.review(clean, self.profile, input_classes=("public", "dossier_1")).status, "PASS")
        self.assertEqual(persona_twin.review(clean, self.profile, channel="hinge", mode="official-api").status, "BLOCK")
        self.assertEqual(persona_twin.review(clean, self.profile, channel="hinge", mode="draft").status, "PASS")
        self.assertEqual(persona_twin.review(clean, self.profile, channel="blog", mode="auto-send").status, "BLOCK")

    def test_flag_off_drops_style_checks_but_never_privacy(self):
        with mock.patch.dict(os.environ, {"ENABLE_PERSONA_TWIN": "false"}):
            self.assertEqual(persona_twin.review("Let's delve into it.", self.profile).status, "PASS")
            self.assertEqual(persona_twin.review("News from Acme Widgets.", self.profile).status, "BLOCK")

    def test_model_critic_can_add_but_not_clear(self):
        clean = "I fixed my bike today. It rides well."
        self.assertEqual(persona_twin.review(clean, self.profile, critic=lambda d: ["sounds stiff"]).status, "REWRITE")
        self.assertEqual(persona_twin.review("Let's delve in.", self.profile, critic=lambda d: []).status, "REWRITE")
        def broken(_):
            raise RuntimeError("model down")
        self.assertEqual(persona_twin.review(clean, self.profile, critic=broken).status, "PASS")

    def test_system_context_carries_style_but_not_red_lines(self):
        context = persona_twin.system_context(self.profile)
        self.assertIn("plain words", context)
        self.assertIn("circle back", context)
        self.assertNotIn("Acme", context)
        self.assertEqual(self.profile.never_disclose, ("Acme Widgets",))

    def test_cadence_drift_is_flagged(self):
        long = " ".join(["This sentence simply keeps going with clause after clause after clause and never once stops to breathe or to let the reader rest for a moment because it was written by a machine that likes length."] * 5)
        self.assertIn("cadence-sentence-length", {f.rule for f in persona_twin.review(long, self.profile).findings})

    def test_agent_proposal_is_refused_by_critic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime" / "inbox").mkdir(parents=True, mode=0o700)
            (root / "runtime").chmod(0o700)
            (root / "runtime" / "inbox" / "persona_style.md").write_text(STYLE)
            with Ledger(root) as ledger:
                book = ApprovalBook(ledger, b"k" * 32)
                with self.assertRaisesRegex(agent_loop.ToolError, "CRITIC_BLOCK"):
                    agent_loop._propose(book, "run1", 1, {"kind": "external-post", "payload": {"text": "Life at Acme Widgets."}}, root)
                result = agent_loop._propose(book, "run1", 1, {"kind": "external-post", "payload": {"text": "I fixed my bike today. It rides well."}}, root)
                self.assertEqual((result["state"], result["executed"]), ("PENDING", False))


class EvolutionTests(unittest.TestCase):
    def examples(self, n=40):
        liked = {"features": {"text": "london singles mixer", "is_weekend_or_friday_evening": True}, "label": 1}
        disliked = {"features": {"text": "tech networking breakfast", "is_weekend_or_friday_evening": False}, "label": 0}
        odd = {"features": {"text": "founders pitch night", "is_weekend_or_friday_evening": False}, "label": 1}
        return [liked, disliked, odd, disliked] * (n // 4)

    def test_guard_accepts_weight_changes_only(self):
        self.assertEqual(guard.violations(BASE, mutated('"founders": 0.5', '"founders": 3.0')), [])

    def test_guard_rejects_everything_else(self):
        cases = {
            "import": mutated("WEEKEND_BONUS = 0.5", "import socket\nWEEKEND_BONUS = 0.5"),
            "call": mutated("WEEKEND_BONUS = 0.5", "WEEKEND_BONUS = open('/etc/passwd')"),
            "attr": mutated("WEEKEND_BONUS = 0.5", "WEEKEND_BONUS = ().__class__"),
            "newname": mutated("WEEKEND_BONUS = 0.5", "WEEKEND_BONUS = 0.5\nMONTHLY_HARD_CAP_PENCE = 999999"),
            "outside": BASE.replace("return max(-10.0, min(10.0, float(total)))", "return 10.0"),
            "markers": BASE.replace(guard.END, ""),
            "missing": mutated("WEEKEND_BONUS = 0.5\n", ""),
        }
        for name, source in cases.items():
            self.assertTrue(guard.violations(BASE, source), name)
            self.assertEqual(evaluator.evaluate_source(source, "unused", self.examples())["combined_score"], -999.0, name)

    def test_sandbox_itself_denies_network_files_and_long_cpu(self):
        """Second wall: even a candidate that somehow skipped the guard cannot reach out."""
        attacks = {
            "network": "import socket\n    socket.socket().connect(('1.1.1.1', 80))",
            "dns": "import socket\n    socket.getaddrinfo('example.com', 80)",
            "file-write": "import io\n    f = io.open(TARGET, 'w'); f.write('x' * 4096); f.flush()",
            "spawn": "import os\n    os.system('true') and None\n    os.fork()",
            "cpu": "while True: pass",
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "escaped.txt"
            for name, body in attacks.items():
                program = Path(tmp) / f"{name}.py"
                program.write_text(f"TARGET = {str(target)!r}\ndef score_event(features):\n    {body}\n    return 1.0\n")
                with self.assertRaises(Exception, msg=name):
                    evaluator.run_candidate(str(program), self.examples(8))
            self.assertFalse(target.exists() and target.stat().st_size > 0)

    def test_bootstrap_until_enough_real_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Ledger(Path(tmp)) as ledger:
                examples, mode = evaluator.select_benchmark(ledger)
                self.assertEqual((mode, len(examples)), ("BOOTSTRAP", len(bootstrap.fixtures())))
                with mock.patch.object(evaluator, "benchmark_from_ledger", return_value=self.examples(40)):
                    self.assertEqual(evaluator.select_benchmark(ledger)[1], "REAL")
                    self.assertEqual(evaluator.select_benchmark(ledger, min_real=5)[1], "REAL")
                with mock.patch.object(evaluator, "benchmark_from_ledger", return_value=self.examples(28)):
                    self.assertEqual(evaluator.select_benchmark(ledger, min_real=5)[1], "BOOTSTRAP")   # floor of 30 holds
        self.assertEqual(evaluator.evaluate_source(BASE, str(evaluator.BASELINE), bootstrap.fixtures())["status"], "SCORED")

    def test_config_can_only_tighten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("min_improvement: 0.001\nmin_real_outcomes: 1\ncpu_seconds: 600\nmonthly_cap_pence: 99999\ncandidates_per_run: 9999\n")
            self.assertEqual(config.load(path), {"min_improvement": 0.05, "min_real_outcomes": 30, "cpu_seconds": 5,
                                                 "candidates_per_run": 50, "monthly_cap_pence": 500})
        self.assertEqual(config.load()["min_improvement"], 0.05)

    def test_mutations_stay_inside_the_block_and_pass_the_guard(self):
        rng = random.Random(7)
        seen = set()
        for _ in range(40):
            candidate = mutate.mutate(BASE, rng)
            self.assertEqual(guard.violations(BASE, candidate), [])
            seen.add(candidate)
        self.assertGreater(len(seen), 20)

    def test_scheduled_run_is_flag_gated_and_halts_at_the_human_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Ledger(Path(tmp)) as ledger:
                book = ApprovalBook(ledger, b"k" * 32)
                with mock.patch.dict(os.environ, {"ENABLE_EVOLUTION_SANDBOX": "false"}):
                    self.assertEqual(promote_gate.run_generation(ledger, book, 1)["status"], "DISABLED")
                notices = []
                with mock.patch.dict(os.environ, {"ENABLE_EVOLUTION_SANDBOX": "true"}):
                    first = next(r for r in (promote_gate.run_generation(ledger, book, seed, notices.append, now=1_800_000_000.0 + seed)
                                             for seed in range(1, 30)) if r["status"].startswith("PROPOSED"))
                    again = promote_gate.run_generation(ledger, book, 99)
                self.assertEqual((first["status"], first["mode"]), ("PROPOSED_PENDING", "BOOTSTRAP"))
                self.assertEqual(again["status"], "WAITING_FOR_OWNER")
                self.assertEqual(len(notices), 1)
                row = dict(zip([c[1] for c in ledger.db.execute("PRAGMA table_info(proposals)")],
                               ledger.db.execute("SELECT * FROM proposals").fetchone()))
                self.assertEqual((row["kind"], row["state"]), ("evolution-promote", "PENDING"))
                self.assertIn("BOOTSTRAP", " ".join(str(v) for v in row.values()))
        self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), BASE)          # still nothing merged

    def test_gate_proposes_only_real_improvement_and_never_merges(self):
        better = mutated('"founders": 0.5', '"founders": 3.0').replace('"tech": 1.0', '"tech": -1.0').replace('"networking": 1.5', '"networking": 0.0')
        with tempfile.TemporaryDirectory() as tmp:
            with Ledger(Path(tmp)) as ledger:
                book = ApprovalBook(ledger, b"k" * 32)
                notices = []
                none = promote_gate.consider(ledger, book, better, "g0", self.examples(4))
                same = promote_gate.consider(ledger, book, BASE, "g1", self.examples())
                unsafe = promote_gate.consider(ledger, book, mutated("WEEKEND_BONUS = 0.5", "import os\nWEEKEND_BONUS = 0.5"), "g2", self.examples())
                good = promote_gate.consider(ledger, book, better, "g3", self.examples(), notify=notices.append)
                self.assertEqual([none["decision"], same["decision"], unsafe["decision"]], ["NOT_ENOUGH_EXAMPLES", "NO_IMPROVEMENT", "REJECTED_UNSAFE"])
                self.assertEqual(good["decision"], "PROPOSED_PENDING")
                self.assertGreaterEqual(good["candidate_score"], good["baseline_score"] * 1.05)
                self.assertEqual(notices, [good["detail"]])
                row = ledger.db.execute("SELECT kind, proposer, state FROM proposals").fetchall()
                self.assertEqual(row, [("evolution-promote", "agent:evolution-lab", "PENDING")])
                self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM evolution_log").fetchone()[0], 4)
        self.assertEqual(evaluator.BASELINE.read_text(encoding="utf-8"), BASE)          # nothing was merged

    def test_benchmark_comes_from_rated_facts(self):
        import json
        from apex.kernel import facts
        with tempfile.TemporaryDirectory() as tmp:
            with Ledger(Path(tmp)) as ledger:
                a = facts.assert_fact(ledger, "owner", "scout_event_1_0", json.dumps({"text": "singles mixer"}), "scout_events")
                facts.assert_fact(ledger, "owner", "scout_event_1_1", json.dumps({"text": "unrated"}), "scout_events")
                facts.record_outcome(ledger, a, "accepted")
                self.assertEqual(evaluator.benchmark_from_ledger(ledger), [{"features": {"text": "singles mixer"}, "label": 1}])

    def test_mutation_sub_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Ledger(Path(tmp)) as ledger:
                clock = [1_800_000_000.0]
                budget = Budget(ledger, clock=lambda: clock[0])
                budget.set_price("anthropic", "evolution-step", 200_000, clock[0] - 10, "test: 200p per call")
                budget.set_cap("intelligence", "month", 100_000)
                promote_gate.reserve_mutation(budget, "evo.1")
                promote_gate.reserve_mutation(budget, "evo.2")
                with self.assertRaisesRegex(BudgetDenied, "EVOLUTION_SUB_CAP"):
                    promote_gate.reserve_mutation(budget, "evo.3")                     # 400p spent + 200p > 500p


if __name__ == "__main__":
    unittest.main()
