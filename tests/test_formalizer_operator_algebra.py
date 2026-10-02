# -*- coding: utf-8 -*-
"""WP3.1 — Operator algebra + FunctionRegistry v2 tests (V7 §6.2/§15)."""

import unittest

from ah.formalizer.operator_algebra import OPERATORS, FunctionRegistryV2, OperatorSpec, RegistryReject


class TestOperatorAlgebra(unittest.TestCase):
    def setUp(self):
        self.r = FunctionRegistryV2()

    def test_commutative_operators_canonicalize_by_sorting_args(self):
        for op in ("AND", "OR", "XOR", "ASSOCIATION"):
            self.assertEqual(self.r.canonical_key(op, ["b", "a"]), self.r.canonical_key(op, ["a", "b"]))

    def test_implies_preserves_argument_order(self):
        self.assertNotEqual(self.r.canonical_key("IMPLIES", ["p", "q"]), self.r.canonical_key("IMPLIES", ["q", "p"]))
        self.assertEqual(self.r.ops["IMPLIES"].arg_order_matters, True)

    def test_unknown_function_rejected_at_write_boundary(self):
        for call in (lambda: self.r.canonical_key("NOPE", ["a"]),
                     lambda: self.r.inferable("NOPE", "X"),
                     lambda: self.r.prohibited("NOPE", "X")):
            with self.assertRaises(RegistryReject):
                call()

    def test_arity_violation_rejected(self):
        with self.assertRaises(RegistryReject):
            self.r.canonical_key("NOT", ["a", "b"])     # NOT is unary
        with self.assertRaises(RegistryReject):
            self.r.canonical_key("AND", ["only_one"])   # AND needs >= 2

    def test_inference_rules_membership(self):
        self.assertTrue(self.r.inferable("AND", "AND_ELIMINATION"))
        self.assertFalse(self.r.inferable("NOT", "AND_ELIMINATION"))
        self.assertTrue(self.r.inferable("IMPLIES", "MODUS_PONENS"))
        self.assertTrue(self.r.inferable("OR", "OR_ELIMINATION"))

    def test_prohibitions(self):
        self.assertTrue(self.r.prohibited("IMPLIES", "AFFIRMING_CONSEQUENT"))
        self.assertTrue(self.r.prohibited("POSSIBLE", "POSSIBILITY_TO_NECESSITY"))
        self.assertTrue(self.r.prohibited("COUNTERFACTUAL", "TREAT_AS_IMPLIES"))

    def test_counterfactual_has_no_classical_inference_rules(self):
        self.assertEqual(OPERATORS["COUNTERFACTUAL"].inference_rules, frozenset())
        self.assertFalse(self.r.inferable("COUNTERFACTUAL", "MODUS_PONENS"))

    def test_register_new_operator_is_a_resource_declaration(self):
        spec = OperatorSpec("IMPLIES_WEAK", 2, 2, False, False,
                            inference_rules=frozenset({"WEAK_MP"}), prohibitions=frozenset())
        self.r.register(spec)
        self.assertTrue(self.r.has("IMPLIES_WEAK"))
        self.assertTrue(self.r.inferable("IMPLIES_WEAK", "WEAK_MP"))


if __name__ == "__main__":
    unittest.main()
