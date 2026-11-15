"""Data boundary / single-active-system freeze (mission 2026-11-15). Gate P2: proves
select_active() skips frozen systems by default and includes them only on explicit
override - the pure logic agents_runner.py --once / --include-frozen relies on."""
import unittest

from apex import agents_governing as ag

ALL_SEVEN_RUNNER_AGENTS = ("strategic_intelligence", "career_industry", "financial_intelligence",
                           "health_longevity", "evidence_verification", "social_relational",
                           "scientific_research")


class FrozenRegistryTests(unittest.TestCase):
    def test_four_named_systems_are_frozen(self):
        self.assertEqual(set(ag.FROZEN), {"financial_intelligence", "mutual_match_platform",
                                          "marketing_funnel", "webxr_twin"})

    def test_no_role_status_was_touched(self):
        statuses = {r.name: r.status for r in ag.ROLES}
        self.assertEqual(statuses["Financial Intelligence"], ag.IMPLEMENTED_LOCAL)
        self.assertEqual(statuses["Social & Relational"], ag.IMPLEMENTED_LOCAL)


class SelectActiveTests(unittest.TestCase):
    def test_default_skips_only_financial_intelligence_among_runner_agents(self):
        active, skipped = ag.select_active(ALL_SEVEN_RUNNER_AGENTS)
        self.assertNotIn("financial_intelligence", active)
        self.assertIn("social_relational", active)
        self.assertEqual(set(skipped), {"financial_intelligence"})

    def test_social_relational_is_not_alone_today(self):
        """Honest gap (docs/FROZEN_SYSTEMS.md): ACTIVE_SYSTEM.md declares A-10 the only
        active system, but the mission's own FROZEN list only names financial_intelligence
        among the 7 agents_runner.py roles - so 6, not 1, run by default today."""
        active, _ = ag.select_active(ALL_SEVEN_RUNNER_AGENTS)
        self.assertEqual(len(active), 6)

    def test_include_frozen_override_restores_it_and_is_reversible(self):
        active, skipped = ag.select_active(ALL_SEVEN_RUNNER_AGENTS, include_frozen=["financial_intelligence"])
        self.assertIn("financial_intelligence", active)
        self.assertEqual(skipped, {})
        # calling again without the override proves freeze was never deleted
        active2, skipped2 = ag.select_active(ALL_SEVEN_RUNNER_AGENTS)
        self.assertNotIn("financial_intelligence", active2)
        self.assertIn("financial_intelligence", skipped2)

    def test_names_not_in_frozen_are_always_active(self):
        active, skipped = ag.select_active(["social_relational", "strategic_intelligence"])
        self.assertEqual(active, ["social_relational", "strategic_intelligence"])
        self.assertEqual(skipped, {})

    def test_mutual_match_marketing_webxr_are_frozen_but_never_runner_agents(self):
        """Confirms the three never collide with agents_runner.py's actual factory keys -
        they are frozen in docs/registry only, per docs/FROZEN_SYSTEMS.md's own caveat."""
        for name in ("mutual_match_platform", "marketing_funnel", "webxr_twin"):
            self.assertNotIn(name, ALL_SEVEN_RUNNER_AGENTS)
            self.assertIn(name, ag.FROZEN)


if __name__ == "__main__":
    unittest.main()
