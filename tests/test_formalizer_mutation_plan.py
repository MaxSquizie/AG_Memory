# -*- coding: utf-8 -*-
"""I19 — typed execution layer for a commit plan (mutation_plan).

Proves the two defects the audit names are closed at the writer, not left to an external caller:

* **D1** — every op's domain/role/operator is validated against the CLOSED sets before materialization; an unknown
  value yields a named ``PlanIssue`` and :func:`execute_plan` refuses the plan WHOLE (fail-closed), never partially.
* **D2** — each asserted fact gets its O/C/W ground attached to the proof graph (§7.4); a fact whose only "grounds"
  are interpretation-only (M/D) is NOT F-visible and surfaces in ``ungrounded_facts`` (ties the writer to SOM).

Plus composition: :func:`from_store_ops` lifts opaque StoreOps into typed mutations, so the legacy writer's gap
(a fact with no ground) is surfaced honestly rather than hidden.
"""

import unittest

from ah.formalizer.mutation_plan import (
    ExecutionResult,
    MutationPlanV2,
    PlanValidationError,
    TypedMutation,
    attach_fact_supports,
    execute_plan,
    from_store_ops,
    validate_plan,
)
from ah.formalizer.store_interface import StoreOp


def plan(*ops):
    return MutationPlanV2(tuple(ops))


class TestD1TypeValidation(unittest.TestCase):
    def test_valid_plan_passes_validation(self):
        p = plan(
            TypedMutation("f1", "ADD_HYPERNODE", domain="C", roles=("SUBJECT", "OBJECT"), supports=("O",)),
            TypedMutation("s1", "ADD_SYMBOL"),  # domain-less op is fine
        )
        self.assertEqual(validate_plan(p), ())

    def test_invalid_role_is_rejected_with_named_issue(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", roles=("SUBJECT", "BOGUS_ROLE")))
        issues = validate_plan(p)
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0].field, issues[0].value), ("role", "BOGUS_ROLE"))

    def test_unknown_domain_is_rejected(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="X"))
        issues = validate_plan(p)
        self.assertEqual((issues[0].field, issues[0].value), ("domain", "X"))

    def test_unregistered_operator_is_rejected(self):
        p = plan(TypedMutation("s1", "ADD_SCOPE", domain="C", operators=("TELEPORT",)))
        issues = validate_plan(p)
        self.assertEqual((issues[0].field, issues[0].value), ("operator", "TELEPORT"))

    def test_execute_refuses_invalid_plan_whole(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", roles=("NOPE",)))
        with self.assertRaises(PlanValidationError) as ctx:
            execute_plan(p)
        # the error names the offending op/field (fail-closed, not a silent partial write)
        self.assertEqual(ctx.exception.issues[0].op_id, "f1")
        self.assertEqual(ctx.exception.issues[0].field, "role")

    def test_execute_accepts_valid_plan(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", roles=("SUBJECT",), supports=("O",)))
        res = execute_plan(p)  # must not raise
        self.assertIsInstance(res, ExecutionResult)


class TestD2FactSupports(unittest.TestCase):
    def test_fact_with_o_ground_is_f_visible(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", supports=("O",)))
        res = execute_plan(p)
        self.assertTrue(res.f_visible["f1"])
        self.assertEqual(res.ungrounded_facts, ())

    def test_c_and_w_grounds_also_assert(self):
        for ground in ("C", "W"):
            p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", supports=(ground,)))
            self.assertTrue(execute_plan(p).f_visible["f1"], f"{ground} must assert a fact")

    def test_fact_with_only_m_and_d_grounded_is_not_f_visible(self):
        # The core §7.4/SOM property: interpretation-only grounds (M/D) never assert a world fact, so the
        # fact stays ungrounded and is reported — it must not be committed as an asserted fact.
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C", supports=("M", "D")))
        res = execute_plan(p)
        self.assertFalse(res.f_visible["f1"])
        self.assertEqual(res.ungrounded_facts, ("f1",))

    def test_fact_with_no_grounds_is_ungrounded(self):
        p = plan(TypedMutation("f1", "ADD_HYPERNODE", domain="C"))  # no supports at all
        res = execute_plan(p)
        self.assertFalse(res.f_visible["f1"])
        self.assertEqual(res.ungrounded_facts, ("f1",))

    def test_non_fact_ops_are_not_grounded(self):
        p = plan(
            TypedMutation("s1", "ADD_SYMBOL"),
            TypedMutation("l1", "ADD_LINK", domain="C"),
        )
        res = execute_plan(p)
        self.assertEqual(res.f_visible, {})  # no asserted facts -> nothing to ground
        self.assertEqual(res.ungrounded_facts, ())


class TestFromStoreOpsComposition(unittest.TestCase):
    def test_lifts_hypernode_and_surfaces_ungrounded_gap(self):
        # The legacy writer emits a fact op with NO supports; lifting it must surface the gap honestly.
        ops = [StoreOp("ADD_HYPERNODE", {"uid": "f1", "domain": "C", "roles": ["SUBJECT"], "actants": {}})]
        res = execute_plan(from_store_ops(ops))
        self.assertFalse(res.f_visible["f1"])          # no O/C/W ground carried -> not F-visible
        self.assertEqual(res.ungrounded_facts, ("f1",))

    def test_lifted_fact_with_supports_is_grounded(self):
        ops = [StoreOp("ADD_HYPERNODE", {"uid": "f1", "domain": "C", "roles": ["SUBJECT"], "supports": ["O"]})]
        res = execute_plan(from_store_ops(ops))
        self.assertTrue(res.f_visible["f1"])

    def test_lifts_scope_operators_for_validation(self):
        ops = [StoreOp("ADD_SCOPE", {"uid": "s1", "domain": "C", "base_roles": ["SUBJECT"],
                                     "chain": [{"op_type": "TELEPORT"}]})]
        issues = validate_plan(from_store_ops(ops))
        self.assertEqual((issues[0].field, issues[0].value), ("operator", "TELEPORT"))

    def test_valid_scope_chain_lifts_clean(self):
        ops = [StoreOp("ADD_SCOPE", {"uid": "s1", "domain": "C", "base_roles": ["SUBJECT"],
                                     "chain": [{"op_type": "EVERY"}, {"op_type": "NOT"}]})]
        self.assertEqual(validate_plan(from_store_ops(ops)), ())


if __name__ == "__main__":
    unittest.main()
