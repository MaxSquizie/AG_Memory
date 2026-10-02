# -*- coding: utf-8 -*-
"""WP3.2 — Quantifiers tests (V7 §6.2): alpha-normalization, canonical forms, on-demand instantiation, closed numeric domains."""

import unittest

from ah.formalizer.quantifiers import Atom, NumericDomain, Quantified, Var, alpha_normalize, canonical_form, instantiate


class TestQuantifiers(unittest.TestCase):
    def test_alpha_normalization_makes_renamed_variants_equal(self):
        f1 = Quantified("EVERY", "x", Atom("P", (Var("x"),)))
        f2 = Quantified("EVERY", "y", Atom("P", (Var("y"),)))   # same structure, different variable name
        self.assertEqual(canonical_form(f1), canonical_form(f2))
        self.assertEqual(canonical_form(f1), "∀x0.P(x0)")

    def test_nested_pre_order_assignment(self):
        f = Quantified("EVERY", "x", Quantified("SOME", "y", Atom("R", (Var("x"), Var("y")))))
        self.assertEqual(canonical_form(f), "∀x0.∃x1.R(x0,x1)")   # outer binding gets x0, inner x1

    def test_none_and_numeric_canonical_forms(self):
        none = Quantified("NONE", "z", Atom("Bad", (Var("z"),)))
        self.assertEqual(canonical_form(none), "¬∃x0.Bad(x0)")
        num = Quantified("AT_LEAST_N", "w", Atom("Has", (Var("w"),)), count=3)
        self.assertTrue(canonical_form(num).startswith("≥3"))

    def test_instantiation_is_on_demand(self):
        f = Quantified("EVERY", "x", Atom("P", (Var("x"),)))
        inst = instantiate(f, "a")          # explicit call; nothing is auto-instantiated at commit time
        self.assertEqual(canonical_form(inst), "P(a)")

        some = Quantified("SOME", "y", Atom("Q", (Var("y"),)))
        self.assertEqual(canonical_form(instantiate(some, "b")), "Q(b)")

    def test_only_universal_and_existential_instantiate_directly(self):
        for q in ("NONE", "AT_LEAST_N"):
            with self.assertRaises(ValueError):
                instantiate(Quantified(q, "x", Atom("P", (Var("x"),)), count=1 if q == "AT_LEAST_N" else 0), "a")

    def test_closed_numeric_domain_counting(self):
        dom = NumericDomain([1, 2, 3, 4])
        self.assertEqual(dom.satisfy(lambda v: v % 2 == 0), 2)      # closed domain: bounded count
        at_least_2 = Quantified("AT_LEAST_N", "w", Atom("Even", (Var("w"),)), count=2)
        self.assertTrue(canonical_form(at_least_2).startswith("≥2"))


if __name__ == "__main__":
    unittest.main()
