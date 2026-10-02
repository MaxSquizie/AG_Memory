# -*- coding: utf-8 -*-
"""WP3.3 — Inference engine + temporal licenses tests (V7 §6.3/§7.4)."""

import unittest

from ah.formalizer.inference_engine import InferenceEngine
from ah.formalizer.temporal_license import cont, point


class TestInferenceEngine(unittest.TestCase):
    def setUp(self):
        self.e = InferenceEngine()

    def test_admissibility_checked_against_operator_table(self):
        self.assertTrue(self.e.admissible_for_operator("AND", "AND_ELIMINATION"))
        self.assertFalse(self.e.admissible_for_operator("OR", "AND_ELIMINATION"))   # wrong operator
        self.assertTrue(self.e.admissible_for_operator("EVERY", "FORALL_INST"))     # quantifier layer
        self.assertFalse(self.e.admissible_for_operator("AND", "FORALL_INST"))
        self.assertTrue(self.e.admissible_for_operator("IMPLIES", "MODUS_PONENS"))

    def test_derive_interval_intersects_premises(self):
        inter = self.e.derive_interval("AND_ELIMINATION", [cont(0, 5), cont(3, 8)])
        self.assertEqual((inter.lo, inter.hi), (3, 5))

    def test_non_overlapping_premises_give_temporal_mismatch(self):
        self.assertIsNone(self.e.derive_interval("AND_ELIMINATION", [cont(0, 2), cont(5, 7)]))   # TEMPORAL_MISMATCH

    def test_or_elimination_incomplete_until_all_branches_covered(self):
        self.assertEqual(self.e.or_elimination_status(1, 2), "OR_ELIMINATION_INCOMPLETE")
        self.assertEqual(self.e.or_elimination_status(2, 2), "OK")

    def test_derived_time_assertion_carries_provenance(self):
        ta = self.e.derive_time_assertion("AND_ELIMINATION", [cont(0, 5), cont(3, 8)], "c1")
        self.assertEqual(ta["assertion_id"], "c1")
        self.assertEqual((ta["interval"].lo, ta["interval"].hi), (3, 5))
        self.assertEqual(ta["provenance"]["rule"], "AND_ELIMINATION")

    def test_derived_time_assertion_none_on_mismatch(self):
        self.assertIsNone(self.e.derive_time_assertion("AND_ELIMINATION", [cont(0, 2), cont(5, 7)], "c1"))


if __name__ == "__main__":
    unittest.main()
