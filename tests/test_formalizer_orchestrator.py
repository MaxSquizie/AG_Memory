# -*- coding: utf-8 -*-
"""P2 integration — Orchestrator vertical scenarios (V7 §6.4/§8.1/§8.3).

Proves the isolated cores compose on one store: an observation-channel retraction propagates to a dependent goal through the shared
liveness set; an unrelated retraction does not; a fixed decision is immutable under a later retraction; and a premise backed by two
observations survives the retraction of one.
"""

import unittest

from ah.formalizer.goal_executor import GoalRequest
from ah.formalizer.orchestrator import Orchestrator
from ah.formalizer.recovery import GoalJournalRecord
from ah.formalizer.temporal_license import point, cont


def _pend(run_id, premises, sig="P1"):
    return GoalJournalRecord(run_id, "OR_ELIMINATION", premises, sig, (point(5), cont(3, 7)))


class TestOrchestratorVertical(unittest.TestCase):
    def test_retraction_kills_dependent_goal_premise(self):
        o = Orchestrator()
        o.register_observation(("O1", 0), {"s_or", "s_not"})

        self.assertEqual(o.recover(_pend("runA", ("s_or", "s_not")))["outcome"], "APPLIED")   # live -> applied

        killed = o.retract_observation(("O1", 0))       # sole backer retracted -> both premises die
        self.assertEqual(killed, ["s_not", "s_or"])

        res = o.recover(_pend("runB", ("s_or", "s_not"), sig="P2"))
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res.get("reason"), "GOAL_PREMISES_STALE")   # retraction propagated to the goal channel

    def test_unrelated_retraction_leaves_goal_applied(self):
        o = Orchestrator()
        o.register_observation(("O1", 0), {"s_or", "s_not"})
        o.register_observation(("O2", 0), {"other"})

        self.assertEqual(o.recover(_pend("runA", ("s_or", "s_not")))["outcome"], "APPLIED")
        o.retract_observation(("O2", 0))               # unrelated observation dies

        res = o.recover(_pend("runB", ("s_or", "s_not"), sig="P1b"))   # fresh, premises still live via O1
        self.assertEqual(res["outcome"], "APPLIED")

    def test_decision_immutable_under_later_retraction(self):
        o = Orchestrator()
        o.register_observation(("O1", 0), {"s_or", "s_not"})
        pend = _pend("runA", ("s_or", "s_not"))

        first = o.recover(pend)                        # APPLIED (fixed historical fact)
        self.assertEqual(first["outcome"], "APPLIED")
        o.retract_observation(("O1", 0))              # a later retraction supersedes the node by cascade...
        second = o.recover(pend)                       # ...but never rewrites the decision (idempotent R0)
        self.assertEqual(second, first)

    def test_premise_backed_by_two_observations_survives_one_retraction(self):
        o = Orchestrator()
        o.register_observation(("O1", 0), {"s_x"})
        o.register_observation(("O2", 0), {"s_x"})     # the same premise is backed by two observations

        self.assertEqual(o.recover(_pend("runA", ("s_x",)))["outcome"], "APPLIED")
        o.retract_observation(("O1", 0))              # O2 still backs s_x -> it stays live

        res = o.recover(_pend("runB", ("s_x",)))      # dedup hit, premise alive via O2
        self.assertEqual(res["outcome"], "APPLIED_NOOP")


if __name__ == "__main__":
    unittest.main()
