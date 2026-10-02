# -*- coding: utf-8 -*-
"""WP2.6 remainder — TemporalLedger visibility adapter + two-level retraction tests (V7 §7.4/§8.2)."""

import unittest

from ah.formalizer.temporal_adapter import TemporalAdapter, TemporalEvidence


class TestTemporalVisibility(unittest.TestCase):
    def test_effective_visibility_requires_all_three(self):
        ta = TemporalAdapter([TemporalEvidence("a1", "N1", "s1", "OBSERVATION", ("O1", 0))])
        ta.set_support_live("s1", True)
        ta.set_node_visible("N1", True)
        self.assertTrue(ta.effective_visibility("a1"))

        ta.set_node_visible("N1", False)          # node not F-visible -> not effectively visible
        self.assertFalse(ta.effective_visibility("a1"))
        ta.set_node_visible("N1", True)
        ta.set_support_live("s1", False)         # support dead -> not effectively visible
        self.assertFalse(ta.effective_visibility("a1"))

    def test_path_death_at_live_observation_keeps_status_live(self):
        """Two-level (a): the path dies but the source observation is live -> status stays LIVE, only visibility drops."""
        ta = TemporalAdapter([TemporalEvidence("a1", "N1", "s1", "OBSERVATION", ("O1", 0))])
        ta.set_support_live("s1", True)
        ta.set_node_visible("N1", True)

        ta.set_support_live("s1", False)         # the supporting path dies (upstream premise retracted), O1 still live
        self.assertFalse(ta.effective_visibility("a1"))
        self.assertEqual(ta.evidences["a1"].status, "LIVE")   # no RETRACTED write on path death

    def test_observation_retraction_writes_retracted_and_spares_goal_runs(self):
        """Two-level (b): OBSERVATION-sourced matching assertions -> RETRACTED; GOAL_RUN-sourced are not touched."""
        ta = TemporalAdapter([
            TemporalEvidence("a1", "N1", "s1", "OBSERVATION", ("O1", 0)),
            TemporalEvidence("g1", "N2", "s2", "GOAL_RUN"),   # goal-derived, no observation tag
        ])
        ta.set_support_live("s1", True)
        ta.set_node_visible("N1", True)

        retracted = ta.retract_observation(("O1", 0))
        self.assertEqual(retracted, ["a1"])
        self.assertEqual(ta.evidences["a1"].status, "RETRACTED")
        self.assertEqual(ta.evidences["g1"].status, "LIVE")   # goal-derived evidence is not retracted by observation retraction


if __name__ == "__main__":
    unittest.main()
