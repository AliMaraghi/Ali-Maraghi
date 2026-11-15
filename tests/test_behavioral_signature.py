"""Behavioral text signature (mission 2026-11-15, Phase 6). Gate P6: trains on synthetic
data, reports precision/recall on a HELD-OUT split, shown raw regardless of the number."""
import unittest

from apex.kernel import behavioral_signature as bs


class BehavioralSignatureTests(unittest.TestCase):
    def test_synthetic_generator_produces_the_requested_counts(self):
        rows = bs.generate_synthetic(50, 50)
        self.assertEqual(len(rows), 100)
        self.assertEqual(sum(r.label for r in rows), 50)
        self.assertEqual(sum(1 - r.label for r in rows), 50)

    def test_split_is_disjoint_and_covers_everything(self):
        rows = bs.generate_synthetic(50, 50)
        train, test = bs.train_test_split(rows)
        self.assertEqual(len(train) + len(test), 100)
        self.assertEqual(set(id(r) for r in train) & set(id(r) for r in test), set())

    def test_report_runs_and_returns_honest_metrics_on_held_out_data(self):
        report = bs.run_report()
        self.assertEqual(report["n_train"], 80)
        self.assertEqual(report["n_test"], 20)
        for split in ("train", "test"):
            m = report[split]
            self.assertTrue(0.0 <= m["precision"] <= 1.0)
            self.assertTrue(0.0 <= m["recall"] <= 1.0)
            self.assertTrue(0.0 <= m["accuracy"] <= 1.0)
            self.assertEqual(m["tp"] + m["fp"] + m["fn"] + m["tn"],
                             report["n_train"] if split == "train" else report["n_test"])

    def test_held_out_accuracy_beats_a_coin_flip_on_this_synthetic_signal(self):
        """Not a claim about any real owner's preferences - this synthetic set has a
        hand-designed signal (length/hour/action-kind), so a correctly-learning classifier
        should clear 0.5 on it. If this ever fails, the pipeline itself is broken, not the
        (nonexistent) real data."""
        report = bs.run_report()
        self.assertGreater(report["test"]["accuracy"], 0.5)

    def test_predict_proba_is_bounded(self):
        rows = bs.generate_synthetic(10, 10)
        weights = bs.train_logistic_regression(rows)
        for r in rows:
            p = bs.predict_proba(weights, r)
            self.assertTrue(0.0 <= p <= 1.0)


if __name__ == "__main__":
    unittest.main()
