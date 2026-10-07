# -*- coding: utf-8 -*-
"""WP2.8 — GoalExecutor goal transaction tests (V7 §6.4/§7.5).

Proves idempotency by goal_run_id, the preflight temporal license gate, premise-liveness re-checked inside the atomic
transaction (the DB-N race), dedup APPLIED_NOOP vs ABORTED-on-stale, FORALL_INST licensing, and decision immutability under
a later retraction.
"""

import unittest

from ah.formalizer.goal_executor import GoalExecutor, GoalRequest, GoalStore, PathRecord, _path_key
from ah.formalizer.temporal_license import point, cont


def _executor(*live):
    store = GoalStore()
    store.live_premises.update(live)
    return GoalExecutor(store), store


class TestGoalTransaction(unittest.TestCase):
    def test_fresh_licensed_live_applies_and_is_idempotent(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("run1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))

        first = ex.execute(req)
        self.assertEqual(first["outcome"], "APPLIED")
        self.assertIn("conclusion_ref", first)
        self.assertEqual(len(store.paths), 1)
        self.assertEqual(len(store.terminals), 1)

        second = ex.execute(req)                       # same goal_run_id -> idempotent no-op
        self.assertEqual(second, first)
        self.assertEqual(len(store.paths), 1)          # no duplicate path
        self.assertEqual(len(store.terminals), 1)      # exactly one terminal per run

    def test_license_failure_aborts_without_node(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("run2", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(9), cont(3, 7)))  # NOT region misses

        res = ex.execute(req)
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_LICENSE_FAILED")
        self.assertEqual(len(store.paths), 0)          # no node/path created on license failure

    def test_premise_dead_inside_transaction_aborts(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("run3", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))

        res = ex.execute(req, interleave=lambda: store.retract_premise("s_not"))   # retraction commits before apply
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_PREMISES_STALE")
        self.assertEqual(len(store.paths), 0)          # no partial records

    def test_dedup_hit_live_is_noop(self):
        ex, store = _executor("s1")
        node_id = store.ensure_node("P1")
        key = ("OR_ELIMINATION", ("s1",), "P1")
        store.paths[key] = PathRecord(record_id="DS0", rule_id="OR_ELIMINATION", premise_support_ids=("s1",), node_id=node_id)

        req = GoalRequest("run4", "OR_ELIMINATION", ("s1",), "P1", (point(5), cont(3, 7)))
        res = ex.execute(req)
        self.assertEqual(res["outcome"], "APPLIED_NOOP")
        self.assertEqual(len(store.paths), 1)          # no second path

    def test_dedup_hit_stale_aborts_without_resurrecting(self):
        ex, store = _executor("s1")
        node_id = store.ensure_node("P1")
        key = ("OR_ELIMINATION", ("s1",), "P1")
        store.paths[key] = PathRecord(record_id="DS0", rule_id="OR_ELIMINATION", premise_support_ids=("s1",), node_id=node_id)

        req = GoalRequest("run5", "OR_ELIMINATION", ("s1",), "P1", (point(5), cont(3, 7)))
        res = ex.execute(req, interleave=lambda: store.retract_premise("s1"))   # existing path's premise dies
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_PREMISES_STALE")
        self.assertEqual(len(store.paths), 1)          # not resurrected, no duplicate

    def test_forall_inst_licensed_and_disjoint(self):
        ex, store = _executor("s_all", "s_p")
        ok = GoalRequest("run6", "FORALL_INST", ("s_all", "s_p"), "P(a)", (cont(0, 10), point(5)))
        self.assertEqual(ex.execute(ok)["outcome"], "APPLIED")

        bad = GoalRequest("run7", "FORALL_INST", ("s_all", "s_p"), "P(b)", (cont(0, 2), point(5)))  # disjoint
        res = ex.execute(bad)
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_LICENSE_FAILED")

    def test_decision_is_immutable_under_later_retraction(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("run8", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))
        first = ex.execute(req)
        self.assertEqual(first["outcome"], "APPLIED")

        store.retract_premise("s_not")                 # a later retraction supersedes the node by cascade...
        self.assertEqual(store.decisions["run8"]["outcome"], "APPLIED")   # ...but never rewrites the decision


class TestI25RegistryAndForm(unittest.TestCase):
    """I25: the executor must not trust rule_id blindly — unknown rules are rejected before any write, and a
    supplied conclusion operator that mismatches the rule's declared form is refused."""

    def test_unknown_rule_is_rejected_before_any_write(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("runX", "NOT_A_REGISTERED_RULE", ("s_or",), "P1", (point(5), cont(3, 7)))

        res = ex.execute(req)
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_RULE_UNKNOWN")
        self.assertEqual(len(store.paths), 0)   # no derived path written for an unknown rule
        self.assertEqual(len(store.nodes), 0)   # and no node materialized

    def test_form_mismatch_is_rejected(self):
        ex, store = _executor("s_or", "s_not")
        # OR_ELIMINATION concludes a disjunction (operator OR); claiming the conclusion is an AND-form is malformed.
        req = GoalRequest("runY", "OR_ELIMINATION", ("s_or", "s_not"), "P1",
                         (point(5), cont(3, 7)), conclusion_operator="AND")

        res = ex.execute(req)
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_FORM_MISMATCH")
        self.assertEqual(len(store.paths), 0)

    def test_correct_conclusion_operator_proceeds(self):
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("runZ", "OR_ELIMINATION", ("s_or", "s_not"), "P1",
                         (point(5), cont(3, 7)), conclusion_operator="OR")

        res = ex.execute(req)
        self.assertEqual(res["outcome"], "APPLIED")   # form matches the rule's declared operator -> proceeds
        self.assertEqual(len(store.paths), 1)

    def test_empty_premises_are_rejected_before_any_write(self):
        # I25: a registered rule with an EMPTY premise set is an ungrounded conclusion -> refused, no node/path.
        ex, store = _executor("s_or", "s_not")
        req = GoalRequest("runE", "OR_ELIMINATION", (), "P1", (point(5), cont(3, 7)))

        res = ex.execute(req)
        self.assertEqual(res["outcome"], "ABORTED")
        self.assertEqual(res["reason"], "GOAL_NO_PREMISES")
        self.assertEqual(len(store.paths), 0)   # no derived path for an ungrounded conclusion
        self.assertEqual(len(store.nodes), 0)   # and no node materialized

    def test_custom_rule_table_is_respected(self):
        from ah.formalizer.inference_engine import InferenceRule

        store = GoalStore()
        store.live_premises.update({"s_or"})
        ex = GoalExecutor(store, rules={"MY_RULE": InferenceRule("MY_RULE", "OR", "CONTINUOUS")})

        self.assertEqual(ex.execute(GoalRequest("r1", "MY_RULE", ("s_or",), "P1"))["outcome"], "APPLIED")
        # a rule absent from the supplied table is unknown even if it exists in the default table
        res = ex.execute(GoalRequest("r2", "OR_ELIMINATION", ("s_or",), "P1"))
        self.assertEqual(res["reason"], "GOAL_RULE_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
