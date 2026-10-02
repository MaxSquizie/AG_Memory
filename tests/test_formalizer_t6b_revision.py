# -*- coding: utf-8 -*-
"""WP2.7 — T6b retraction cascade tests (V7 §8.1/§8.2).

Proves the two-level distinction (observation retraction writes RETRACTED; path death at a live observation does not),
the node cascade, independent-path survival keeping a report open, idempotent report closing, and the state-transition
tables (terminal states have no outgoing edge).
"""

import unittest

from ah.formalizer.support_som import Node, ProofGraph
from ah.formalizer.t6b_revision import InvalidTransition, RevisionLedger


def _ledger(*nodes):
    return RevisionLedger(ProofGraph(list(nodes)))


class TestObservationRetraction(unittest.TestCase):
    def test_cascade_supersedes_node_retracts_assertion_closes_report(self):
        led = _ledger(Node("p", "N", True))
        g = led.graph
        s1 = g.add_root_support("p", "O", tag=("O1", 0), record_id="s1")
        led.register_observation("O1")
        led.add_assertion("A1", ("O1", 0), "p", s1.record_id)
        r = led.add_report("R", ["A1"])

        self.assertTrue(led.effective_visibility("A1"))   # open before retraction
        res = led.retract_observation("O1")

        self.assertEqual(res["superseded_nodes"], ["p"])
        self.assertEqual(res["retracted_assertions"], ["A1"])
        self.assertEqual(res["closed_reports"], ["R"])
        self.assertEqual(led.observations["O1"].status, "RETRACTED")
        self.assertEqual(led.assertions["A1"].status, "RETRACTED")
        self.assertEqual(r.closed_by, "RETRACTION")

    def test_path_death_at_live_observation_writes_no_retracted(self):
        """§8.2 case (a): retracting O3 kills the premise path; A2 (grounded by live O2) stays LIVE but its report closes."""
        led = _ledger(Node("p", "N", True), Node("m", "G", True))
        g = led.graph
        g.add_root_support("p", "O", tag=("O3", 0), record_id="sp")          # p grounded by O3
        rd = g.add_derived_support("m", "AND_ELIMINATION", ["p"], ("O2", 0), "rd1")  # m derived from p, tagged O2
        led.register_observation("O3")
        led.register_observation("O2")
        led.add_assertion("A2", ("O2", 0), "m", rd.record_id)
        r = led.add_report("R2", ["A2"])

        self.assertTrue(led.effective_visibility("A2"))   # m visible via the live derived path
        res = led.retract_observation("O3")               # kill the upstream premise, NOT O2

        self.assertEqual(res["retracted_assertions"], [])  # A2 is grounded by O2, not retracted
        self.assertEqual(led.assertions["A2"].status, "LIVE")   # two-level: no RETRACTED write on path death
        self.assertEqual(led.observations["O3"].status, "RETRACTED")
        self.assertFalse(led.effective_visibility("A2"))  # but the path is dead -> not effectively visible
        self.assertEqual(r.closed_by, "RETRACTION")

    def test_independent_path_survives_report_stays_open(self):
        led = _ledger(Node("m", "G", True))
        g = led.graph
        sa = g.add_root_support("m", "O", tag=("Oa", 0), record_id="sa")
        sb = g.add_root_support("m", "O", tag=("Ob", 0), record_id="sb")
        led.register_observation("Oa")
        led.register_observation("Ob")
        led.add_assertion("Ab", ("Ob", 0), "m", sb.record_id)   # assertion grounded by Ob, not Oa
        r = led.add_report("R", ["Ab"])

        res = led.retract_observation("Oa")                    # kill only Oa's path

        self.assertEqual(res["retracted_assertions"], [])
        self.assertEqual(led.assertions["Ab"].status, "LIVE")
        self.assertIn("m", g.f_visible())                       # m still visible via sb
        self.assertTrue(led.effective_visibility("Ab"))
        self.assertIsNone(r.closed_by)                          # report stays OPEN


class TestReportClosingIdempotency(unittest.TestCase):
    def test_close_is_idempotent(self):
        led = _ledger(Node("p", "N", True))
        g = led.graph
        s1 = g.add_root_support("p", "O", tag=("O1", 0), record_id="s1")
        led.register_observation("O1")
        led.add_assertion("A1", ("O1", 0), "p", s1.record_id)
        r = led.add_report("R", ["A1"])

        led.retract_observation("O1")
        self.assertEqual(r.closed_by, "RETRACTION")
        self.assertEqual(led._close_reports(), [])             # no second close
        self.assertEqual(r.closed_by, "RETRACTION")


class TestStateTransitions(unittest.TestCase):
    def test_double_retraction_raises(self):
        led = _ledger(Node("p", "N", True))
        g = led.graph
        s1 = g.add_root_support("p", "O", tag=("O1", 0), record_id="s1")
        led.register_observation("O1")
        led.retract_observation("O1")
        with self.assertRaises(InvalidTransition):
            led.retract_observation("O1")                      # terminal state has no outgoing edge

    def test_illegal_transition_raises(self):
        from ah.formalizer.t6b_revision import _transition
        with self.assertRaises(InvalidTransition):
            _transition("observation", "LIVE", "LIVE")         # not in the allowed set


class TestSupersede(unittest.TestCase):
    def test_atomic_version_switch_supersedes_not_retracts(self):
        led = _ledger(Node("p", "N", True))
        g = led.graph
        s1 = g.add_root_support("p", "O", tag=("O5", 0), record_id="s1")
        led.register_observation("O5")
        led.add_assertion("A1", ("O5", 0), "p", s1.record_id)
        r = led.add_report("R", ["A1"])

        closed = led.supersede_observation("O5")

        self.assertEqual(led.observations["O5"].status, "SUPERSEDED")   # distinct from RETRACTED
        self.assertEqual(led.assertions["A1"].status, "SUPERSEDED")
        self.assertEqual(closed, ["R"])


if __name__ == "__main__":
    unittest.main()
