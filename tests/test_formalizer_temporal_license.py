# -*- coding: utf-8 -*-
"""WP2.5 — temporal license algebra tests (V7 §6.3/§7.4).

Covers every documented row of the OR_ELIMINATION combination table (subset semantics) and the FORALL_INST quantifier
table (intersection semantics), plus the mixed dated/undated, both-undated, degenerate-existential, two-existentials,
and unknown-boundary diagnostics.
"""

import unittest

from ah.formalizer.temporal_license import (
    cont, exist, forall_inst_license, or_elimination_license, point, undated,
)


class TestOrEliminationLicense(unittest.TestCase):
    def test_point_equal(self):
        r = or_elimination_license(point(5), point(5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.point), ("POINT", 5))

    def test_point_different_not_covered(self):
        self.assertEqual(or_elimination_license(point(5), point(6)).status, "UNKNOWN")

    def test_point_in_continuous(self):
        r = or_elimination_license(point(5), cont(3, 7))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.point), ("POINT", 5))

    def test_point_outside_continuous(self):
        self.assertEqual(or_elimination_license(point(9), cont(3, 7)).status, "UNKNOWN")

    def test_existential_subset_of_continuous(self):
        r = or_elimination_license(exist(3, 4), cont(1, 5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, sorted(r.derived_region.points)), ("EXISTENTIAL", [3, 4]))

    def test_existential_not_subset(self):
        self.assertEqual(or_elimination_license(exist(3, 8), cont(1, 5)).status, "UNKNOWN")

    def test_continuous_inside_continuous(self):
        r = or_elimination_license(cont(2, 4), cont(1, 5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.lo, r.derived_region.hi), ("CONTINUOUS", 2, 4))

    def test_continuous_not_inside(self):
        self.assertEqual(or_elimination_license(cont(2, 6), cont(1, 5)).status, "UNKNOWN")

    def test_degenerate_existential_equals_point(self):
        r = or_elimination_license(exist(5), point(5))   # {5} normalizes to POINT(5)
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.point), ("POINT", 5))

    def test_two_nondegenerate_existentials_never_licensed(self):
        self.assertEqual(or_elimination_license(exist(3, 4), exist(3, 4)).status, "UNKNOWN")

    def test_mixed_dated_undated_not_licensed(self):
        r = or_elimination_license(undated(), cont(1, 5))
        self.assertEqual(r.status, "UNKNOWN")
        self.assertEqual(r.diagnostic, "OR_ELIMINATION_TEMPORAL_MISMATCH")

    def test_both_undated_propositional(self):
        r = or_elimination_license(undated(), undated())
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual(r.derived_region.kind, "UNDATED")

    def test_unknown_boundary_diagnostic(self):
        r = or_elimination_license(point(5), cont(None, 7))
        self.assertEqual(r.status, "UNKNOWN")
        self.assertEqual(r.diagnostic, "INTERVAL_BOUNDARY_UNKNOWN")


class TestForallInstLicense(unittest.TestCase):
    def test_point_equal(self):
        r = forall_inst_license(point(5), point(5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.point), ("POINT", 5))

    def test_point_different(self):
        self.assertEqual(forall_inst_license(point(5), point(6)).status, "UNKNOWN")

    def test_point_in_continuous(self):
        r = forall_inst_license(point(3), cont(1, 5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.point), ("POINT", 3))

    def test_continuous_intersection(self):
        r = forall_inst_license(cont(2, 4), cont(3, 6))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, r.derived_region.lo, r.derived_region.hi), ("CONTINUOUS", 3, 4))

    def test_continuous_disjoint(self):
        self.assertEqual(forall_inst_license(cont(1, 2), cont(3, 4)).status, "UNKNOWN")

    def test_existential_subset_of_continuous(self):
        r = forall_inst_license(exist(3, 4), cont(1, 5))
        self.assertEqual(r.status, "LICENSED")
        self.assertEqual((r.derived_region.kind, sorted(r.derived_region.points)), ("EXISTENTIAL", [3, 4]))

    def test_two_existentials_never_licensed(self):
        self.assertEqual(forall_inst_license(exist(3, 4), exist(3, 4)).status, "UNKNOWN")

    def test_mixed_dated_undated(self):
        r = forall_inst_license(undated(), cont(1, 5))
        self.assertEqual(r.status, "UNKNOWN")
        self.assertEqual(r.diagnostic, "FORALL_INST_TEMPORAL_MISMATCH")


if __name__ == "__main__":
    unittest.main()
