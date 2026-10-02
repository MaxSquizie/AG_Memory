# -*- coding: utf-8 -*-
"""WP2.5 — SOM + UsageLink typed layer tests (V7 §7.5).

Proves the s_accessible fixpoint (live base + usage links), the SUPERSEDED cascade by usage dependencies, legal-kind
validation (N→G rejected), and that mutual references without a live base support nothing.
"""

import unittest

from ah.formalizer.usage_layer import UsageLayer


class TestUsageLayer(unittest.TestCase):
    def test_live_base_and_usage_chain(self):
        ul = UsageLayer({"A": {"kind": "G", "asserted": True},
                        "B": {"kind": "N", "asserted": True},
                        "C": {"kind": "N", "asserted": True}})
        ul.set_live("A", True)
        ul.add_link("A", "B")   # G_N
        ul.add_link("B", "C")   # N_N

        self.assertEqual(ul.accessible(), {"A", "B", "C"})
        self.assertTrue(ul.s_accessible("C"))

    def test_nonlive_node_stays_accessible_via_live_source(self):
        ul = UsageLayer({"A": {"kind": "G", "asserted": True}, "B": {"kind": "N", "asserted": True}})
        ul.set_live("A", True)
        ul.add_link("A", "B")   # B is not live, but used by live A

        self.assertEqual(ul.accessible(), {"A", "B"})

    def test_supersede_cascades_through_usage_dependencies(self):
        ul = UsageLayer({"A": {"kind": "G", "asserted": True},
                        "B": {"kind": "N", "asserted": True},
                        "C": {"kind": "N", "asserted": True}})
        ul.set_live("A", True)
        ab = ul.add_link("A", "B")
        bc = ul.add_link("B", "C")

        dropped = ul.supersede("A")   # A drops from live -> B (only via A) -> C (only via B) fall out

        self.assertEqual(dropped, {"A", "B", "C"})
        self.assertEqual(ul.accessible(), set())
        for nid in ("A", "B", "C"):
            self.assertEqual(ul.nodes[nid]["status"], "SUPERSEDED")
        self.assertEqual(ab.status, "SUPERSEDED")
        self.assertEqual(bc.status, "SUPERSEDED")

    def test_illegal_n_to_g_link_rejected(self):
        ul = UsageLayer({"A": {"kind": "N", "asserted": True}, "D": {"kind": "G", "asserted": True}})
        with self.assertRaises(ValueError):
            ul.add_link("A", "D")   # N_G is not a legal usage link

    def test_mutual_references_without_live_base_support_nothing(self):
        ul = UsageLayer({"P": {"kind": "G", "asserted": True}, "Q": {"kind": "G", "asserted": True}})
        ul.add_link("P", "Q")   # G_G
        ul.add_link("Q", "P")   # G_G — a cycle, but neither is live

        self.assertEqual(ul.accessible(), set())


if __name__ == "__main__":
    unittest.main()
