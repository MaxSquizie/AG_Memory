# -*- coding: utf-8 -*-
"""Goal-executor tests (V7 §5.9) — compilation into the REAL AssociationGoal/Ref types."""

import unittest

from ah.inference.contracts import AssociationGoal
from ah.model.types import Ref, RefKind

from ah.formalizer.goal_executor import compile_association_goals, goals_from_ir


def _resolver(mapping: dict[str, Ref | None]):
    return lambda span: mapping.get(span)


class TestCompile(unittest.TestCase):
    def test_two_mentions_yield_one_goal(self):
        refs = {"Ворона": Ref("u1", RefKind.N), "перья": Ref("u2", RefKind.G)}
        goals = compile_association_goals(["Ворона", "перья"], _resolver(refs), text="Ворона имеет перья")
        self.assertEqual(len(goals), 1)
        g = goals[0].goal
        self.assertIsInstance(g, AssociationGoal)
        self.assertEqual((g.left.uid, g.right.uid), ("u1", "u2"))

    def test_l_ref_is_dropped_not_fabricated(self):
        refs = {"Ворона": Ref("u1", RefKind.N), "x": Ref("u9", RefKind.L)}
        goals = compile_association_goals(["Ворона", "x"], _resolver(refs))
        self.assertEqual(goals, [])  # the L endpoint is excluded; no goal fabricated

    def test_unresolvable_span_skipped(self):
        refs = {"Ворона": Ref("u1", RefKind.N)}
        goals = compile_association_goals(["Ворона", "неизвестно"], _resolver(refs))
        self.assertEqual(goals, [])  # only one resolvable mention -> no pair

    def test_deterministic_order_and_dedup(self):
        refs = {s: Ref(f"u{i}", RefKind.N) for i, s in enumerate(["a", "b", "c"])}
        goals = compile_association_goals(["a", "b", "c"], _resolver(refs))
        self.assertEqual([(g.left_span, g.right_span) for g in goals],
                         [("a", "b"), ("a", "c"), ("b", "c")])

        dup = compile_association_goals(["a", "a", "b"], _resolver(refs))
        self.assertEqual([(g.left_span, g.right_span) for g in dup], [("a", "b")])


class TestRealContract(unittest.TestCase):
    def test_real_type_rejects_l(self):
        with self.assertRaises(ValueError):
            AssociationGoal(left=Ref("x", RefKind.L), right=Ref("y", RefKind.N))

    def test_goals_from_ir_uses_lexical_units(self):
        class _IR:
            lexical_units = ("Ворона", "перья")
            predicate_frames = ()
        refs = {"Ворона": Ref("u1", RefKind.N), "перья": Ref("u2", RefKind.G)}
        goals = goals_from_ir(_IR(), _resolver(refs))
        self.assertEqual(len(goals), 1)


if __name__ == "__main__":
    unittest.main()
