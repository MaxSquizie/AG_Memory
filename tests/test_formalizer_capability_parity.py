# -*- coding: utf-8 -*-
"""B — Capability parity vs the legacy formalization stack (V7 §12 / WP3.5).

The legacy modules ``logical_formalization`` / ``modal_formalization`` / ``higher_order_queries`` + ``identity_query`` are
the behavioral reference for what the V7 core must reproduce. Full before/after agreement on *arbitrary* inputs is the job
of the live-model harness (``test_formalizer_legacy_parity``); this module pins **concrete, representative forms** from each
legacy area and proves the V7 core produces the correct result for them — i.e. "core covered" at the unit level:

- **Logical**  -> ``operator_algebra`` + ``temporal_license`` (the DR16 counterexample: a limited-yesterday negation does NOT
  refute a today proposition; a same-window negation licenses OR-elimination).
- **Modal**    -> ``operator_algebra`` modal operators (NOT arity/rule, COUNTERFACTUAL not reducible to IMPLIES, IMPLIES
  non-commutative with fallacy prohibitions, unknown functions rejected at the write boundary).
- **Queries**  -> ``interrogatives`` + ``count_reader`` (request kinds compile to declared goals; unknown kind never becomes a
  bare EXISTS; bounded-count answers are honest: AT_LEAST_N needs no certificate, EXACTLY_N without one is INCOMPLETE_DOMAIN
  but still surfaces the proven lower bound).
"""

import unittest


class LogicalParity(unittest.TestCase):
    def test_limited_negation_does_not_refute_distant_proposition(self):
        # DR16: "Иван или Пётр пришёл сегодня" + "Пётр весь вчерашний день не приходил" -> "Иван пришёл сегодня?" = UNKNOWN.
        from ah.formalizer.temporal_license import or_elimination_license, cont

        today, yesterday = cont(24, 36), cont(0, 12)
        res = or_elimination_license(today, yesterday)   # NOT-branch covers only yesterday; root is today
        self.assertEqual(res.status, "UNKNOWN")

    def test_same_window_negation_licenses_or_elimination(self):
        from ah.formalizer.temporal_license import or_elimination_license, cont

        res = or_elimination_license(cont(0, 12), cont(0, 12))
        self.assertEqual(res.status, "LICENSED")

    def test_mixed_dated_undated_is_unknown(self):
        from ah.formalizer.temporal_license import or_elimination_license, cont, undated

        res = or_elimination_license(undated(), cont(0, 12))
        self.assertEqual(res.status, "UNKNOWN")


class ModalParity(unittest.TestCase):
    def test_not_operator_declared_arity_and_rule(self):
        from ah.formalizer.operator_algebra import OPERATORS

        spec = OPERATORS["NOT"]
        self.assertEqual(spec.arity_min, 1)
        self.assertEqual(spec.arity_max, 1)
        self.assertIn("DOUBLE_NEGATION", spec.inference_rules)

    def test_counterfactual_not_reducible_to_implies(self):
        from ah.formalizer.operator_algebra import OPERATORS

        cf = OPERATORS["COUNTERFACTUAL"]
        self.assertEqual(cf.arity_min, 2)
        self.assertFalse(cf.commutative)
        self.assertIn("TREAT_AS_IMPLIES", cf.prohibitions)

    def test_implies_noncommutative_with_fallacy_prohibitions(self):
        from ah.formalizer.operator_algebra import OPERATORS

        imp = OPERATORS["IMPLIES"]
        self.assertFalse(imp.commutative)
        self.assertTrue(imp.arg_order_matters)
        self.assertIn("AFFIRMING_CONSEQUENT", imp.prohibitions)

    def test_registry_rejects_unknown_function_at_write_boundary(self):
        from ah.formalizer.operator_algebra import FunctionRegistryV2, RegistryReject

        reg = FunctionRegistryV2()
        with self.assertRaises(RegistryReject):
            reg.canonical_key("NOT_A_REAL_OP", ("a",))

    def test_commutative_canonical_form_is_order_insensitive(self):
        from ah.formalizer.operator_algebra import FunctionRegistryV2

        reg = FunctionRegistryV2()
        self.assertEqual(reg.canonical_key("AND", ("b", "a")), reg.canonical_key("AND", ("a", "b")))


class QueryParity(unittest.TestCase):
    def test_who_compiles_to_role_fill(self):
        from ah.formalizer.interrogatives import compile as cquery, ROLE_FILL

        q = cquery("WHO")
        self.assertEqual(q.status, "COMPILED")
        self.assertIn(ROLE_FILL, q.goal_kinds)

    def test_count_compiles_to_count_goal(self):
        from ah.formalizer.interrogatives import compile as cquery, COUNT

        q = cquery("COUNT")
        self.assertEqual(q.status, "COMPILED")
        self.assertIn(COUNT, q.goal_kinds)

    def test_unknown_kind_never_becomes_bare_exists(self):
        from ah.formalizer.interrogatives import compile as cquery, UNKNOWN_INTERROGATIVE, no_arbitrary_exists

        q = cquery("SOME_MADE_UP_KIND")
        self.assertEqual(q.status, "QUERY_TARGET_UNBOUND")
        self.assertEqual(q.reason, UNKNOWN_INTERROGATIVE)
        self.assertTrue(no_arbitrary_exists())

    def test_at_least_n_answered_without_certificate(self):
        from ah.formalizer.interrogatives import answer_count_query
        from ah.formalizer.count_reader import NumericClaim, AT_LEAST_N

        a = answer_count_query(NumericClaim(kind=AT_LEAST_N, bound_value=3))
        self.assertEqual(a.status, "ANSWERED")
        self.assertIn("как минимум 3", a.text)

    def test_exactly_n_without_certificate_is_incomplete_but_bounded(self):
        from ah.formalizer.interrogatives import answer_count_query
        from ah.formalizer.count_reader import NumericClaim, EXACTLY_N, INCOMPLETE_DOMAIN

        a = answer_count_query(NumericClaim(kind=EXACTLY_N, bound_value=3))  # no DomainCertificate
        self.assertEqual(a.status, "UNKNOWN")
        self.assertEqual(a.reason, INCOMPLETE_DOMAIN)
        self.assertEqual(a.lower_bound, 3)   # the proven lower bound is still surfaced

    def test_no_asserted_number_is_unknown(self):
        from ah.formalizer.interrogatives import answer_count_query
        from ah.formalizer.count_reader import NumericClaim, AT_LEAST_N, NO_BOUND_ASSERTED

        a = answer_count_query(NumericClaim(kind=AT_LEAST_N))  # quantifier present, no number
        self.assertEqual(a.status, "UNKNOWN")
        self.assertEqual(a.reason, NO_BOUND_ASSERTED)


if __name__ == "__main__":
    unittest.main()
