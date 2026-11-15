"""Data boundary / single-active-system freeze (mission 2026-11-15, superseded same day).
Gate P1: proves select_active() skips frozen systems by default and includes them only on
explicit override - the pure logic agents_runner.py --once / --include-frozen relies on."""
import unittest

from apex import agents_governing as ag

ALL_SEVEN_RUNNER_AGENTS = ("strategic_intelligence", "career_industry", "financial_intelligence",
                           "health_longevity", "evidence_verification", "social_relational",
                           "scientific_research")
CURRENT_FROZEN = {"digital_twin", "marketing_funnel", "mutual_match_platform", "adult_social_assist"}


class FrozenRegistryTests(unittest.TestCase):
    def test_current_frozen_set_matches_the_superseding_mission(self):
        self.assertEqual(set(ag.FROZEN), CURRENT_FROZEN)

    def test_financial_intelligence_is_not_frozen(self):
        """The first freeze (same day) named financial_intelligence; a later mission this
        session named a different exact 4 and did not - so it is unfrozen now, by design."""
        self.assertNotIn("financial_intelligence", ag.FROZEN)

    def test_no_role_status_was_touched(self):
        statuses = {r.name: r.status for r in ag.ROLES}
        self.assertEqual(statuses["Financial Intelligence"], ag.IMPLEMENTED_LOCAL)
        self.assertEqual(statuses["Social & Relational"], ag.IMPLEMENTED_LOCAL)


class SelectActiveTests(unittest.TestCase):
    def test_none_of_the_current_frozen_names_are_runner_agents(self):
        """Honest gap (docs/FROZEN_SYSTEMS.md): the current FROZEN set is a no-op against
        agents_runner.py's actual execution - all 7 runner agents run on --once today."""
        self.assertTrue(CURRENT_FROZEN.isdisjoint(ALL_SEVEN_RUNNER_AGENTS))
        active, skipped = ag.select_active(ALL_SEVEN_RUNNER_AGENTS)
        self.assertEqual(len(active), 7)
        self.assertEqual(skipped, {})

    def test_a_frozen_name_is_skipped_when_it_is_the_candidate_set(self):
        active, skipped = ag.select_active(["digital_twin", "social_relational"])
        self.assertEqual(active, ["social_relational"])
        self.assertEqual(set(skipped), {"digital_twin"})

    def test_include_frozen_override_restores_it_and_is_reversible(self):
        active, skipped = ag.select_active(["digital_twin", "social_relational"], include_frozen=["digital_twin"])
        self.assertEqual(set(active), {"digital_twin", "social_relational"})
        self.assertEqual(skipped, {})
        active2, skipped2 = ag.select_active(["digital_twin", "social_relational"])
        self.assertNotIn("digital_twin", active2)
        self.assertIn("digital_twin", skipped2)

    def test_names_not_in_frozen_are_always_active(self):
        active, skipped = ag.select_active(["social_relational", "strategic_intelligence"])
        self.assertEqual(active, ["social_relational", "strategic_intelligence"])
        self.assertEqual(skipped, {})


if __name__ == "__main__":
    unittest.main()
