# -*- coding: utf-8 -*-
"""Acceptance tests for the deferred §6.3 query surfaces (V7): bounded-count reader + broad interrogative registry."""

import unittest

from ah.formalizer.count_reader import (
    NumericClaim, answer_count, AT_LEAST_N, EXACTLY_N, AT_MOST_N,
    INCOMPLETE_DOMAIN, NO_BOUND_ASSERTED, UNKNOWN_KIND,
)
from ah.formalizer.interrogatives import (
    REGISTRY, compile, answer_count_query, no_arbitrary_exists,
    UNKNOWN_INTERROGATIVE, CLAUSE_DETECTION_REQUIRED, EXISTS,
)


class TestCountReader(unittest.TestCase):
    def test_at_least_n_renders_lower_bound_without_certificate(self):
        # The user's own example: «Сколько перьев выпало?» по «Минимум 52…» -> «как минимум 52».
        ans = answer_count(NumericClaim(kind=AT_LEAST_N, bound_value=52))
        self.assertEqual(ans.status, "ANSWERED")
        self.assertEqual(ans.text, "как минимум 52")
        self.assertIsNone(ans.reason)

    def test_exactly_n_with_certificate(self):
        ans = answer_count(NumericClaim(kind=EXACTLY_N, bound_value=7, has_certificate=True))
        self.assertEqual((ans.status, ans.text), ("ANSWERED", "ровно 7"))

    def test_exactly_n_without_certificate_is_incomplete_but_bounded(self):
        ans = answer_count(NumericClaim(kind=EXACTLY_N, bound_value=7))
        self.assertEqual(ans.status, "UNKNOWN")
        self.assertEqual(ans.reason, INCOMPLETE_DOMAIN)
        self.assertEqual(ans.lower_bound, 7)   # proven lower bound still surfaced

    def test_at_most_n_with_certificate(self):
        ans = answer_count(NumericClaim(kind=AT_MOST_N, bound_value=3, has_certificate=True))
        self.assertEqual((ans.status, ans.text), ("ANSWERED", "не более 3"))

    def test_at_most_n_without_certificate_is_incomplete(self):
        ans = answer_count(NumericClaim(kind=AT_MOST_N, bound_value=3))
        self.assertEqual((ans.status, ans.reason), ("UNKNOWN", INCOMPLETE_DOMAIN))

    def test_no_bound_asserted(self):
        ans = answer_count(NumericClaim(kind=AT_LEAST_N, bound_value=None))
        self.assertEqual((ans.status, ans.reason), ("UNKNOWN", NO_BOUND_ASSERTED))

    def test_unknown_numeric_kind(self):
        ans = answer_count(NumericClaim(kind="SOME", bound_value=2))
        self.assertEqual((ans.status, ans.reason), ("UNKNOWN", UNKNOWN_KIND))


class TestInterrogatives(unittest.TestCase):
    def test_known_wh_compiles_to_declared_goals(self):
        q = compile("WH_OPEN")
        self.assertEqual(q.status, "COMPILED")
        self.assertIn("RoleFillGoal", q.goal_kinds)

    def test_unknown_kind_never_becomes_exists(self):
        q = compile("TOTALLY_UNKNOWN_KIND")
        self.assertEqual(q.status, "QUERY_TARGET_UNBOUND")
        self.assertEqual(q.reason, UNKNOWN_INTERROGATIVE)
        self.assertEqual(q.goal_kinds, ())   # no arbitrary EXISTS

    def test_if_requires_clause_detection(self):
        without = compile("IF")
        self.assertEqual((without.status, without.reason), ("QUERY_TARGET_UNBOUND", CLAUSE_DETECTION_REQUIRED))
        with_det = compile("IF", clause_detector=object())
        self.assertEqual(with_det.status, "COMPILED")

    def test_hypothetical_is_non_factual_and_clause_scoped(self):
        spec = REGISTRY["HYPOTHETICAL"]
        self.assertTrue(spec.non_factual)
        self.assertTrue(spec.requires_clause)
        self.assertEqual(compile("HYPOTHETICAL").status, "QUERY_TARGET_UNBOUND")

    def test_indirect_request_is_non_factual(self):
        self.assertTrue(REGISTRY["INDIRECT_REQUEST"].non_factual)

    def test_no_arbitrary_exists_invariant(self):
        self.assertTrue(no_arbitrary_exists())

    def test_every_spec_has_explicit_fallback(self):
        for spec in REGISTRY.values():
            self.assertTrue(spec.fallback, f"{spec.request_kind} lacks a fallback")

    def test_count_delegates_to_reader(self):
        ans = answer_count_query(NumericClaim(kind=AT_LEAST_N, bound_value=52))
        self.assertEqual(ans.text, "как минимум 52")


if __name__ == "__main__":
    unittest.main()
