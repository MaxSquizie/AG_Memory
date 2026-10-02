# -*- coding: utf-8 -*-
"""WP2.4 — support ledger + SOM invariant tests (V7 §7.4/§7.5).

Proves the proof-graph liveness core on a pure module: only O/C/W assert a fact (R/D/M/A/P rejected); a live root
support makes a node F-visible; an unasserted structural operand is S-accessible but never F-visible by itself;
retracting an observation SUPERSEDES its orphaned asserted fact and the structural operands under it, while a node
with an independent path survives; a derived path dies when one of its premises stops being visible; and som_violations
flags an asserted fact left with no live, complete support.
"""

import unittest

from ah.formalizer.support_som import (
    FACT_GROUNDS, InvalidFactGround, Node, ProofGraph,
)


class TestSupportWriters(unittest.TestCase):
    def test_only_fact_grounds_accepted(self):
        g = ProofGraph([Node("n", "N", True)])
        for gt in sorted(FACT_GROUNDS):  # O/C/W
            g.add_root_support("n", gt, ("o", 0), f"r{gt}")
        self.assertEqual(len(g.nodes["n"].supports), len(FACT_GROUNDS))

    def test_interpretation_grounds_rejected(self):
        g = ProofGraph([Node("n", "N", True)])
        for bad in ("R", "D", "M", "A", "P"):
            with self.assertRaises(InvalidFactGround):
                g.add_root_support("n", bad, ("o", 0), "x")


class TestVisibility(unittest.TestCase):
    def test_live_root_support_makes_f_visible(self):
        g = ProofGraph([Node("n", "N", True)])
        g.add_root_support("n", "O", ("oA", 0), "r1")
        self.assertIn("n", g.f_visible())

    def test_structural_operand_s_accessible_not_f_visible(self):
        parent = Node("p", "N", True)
        child = Node("c", "N", False, usage_links={"p": "LIVE"})
        g = ProofGraph([parent, child])
        g.add_root_support("p", "O", ("oA", 0), "r1")
        fvis = g.f_visible()
        self.assertIn("p", fvis)
        self.assertNotIn("c", fvis)          # no own path -> never F-visible by itself
        self.assertIn("c", g.s_accessible(fvis))  # reachable via a live link to an F-visible ancestor


class TestRetractionCascade(unittest.TestCase):
    def test_retract_orphans_asserted_and_structural_child(self):
        parent = Node("p", "N", True)
        child = Node("c", "N", False, usage_links={"p": "LIVE"})
        g = ProofGraph([parent, child])
        g.add_root_support("p", "O", ("oA", 0), "r1")
        newly = g.retract(("oA", 0))
        self.assertIn("p", newly)
        self.assertEqual(g.nodes["p"].status, "SUPERSEDED")
        self.assertEqual(g.nodes["c"].status, "SUPERSEDED")  # no own path under a dead parent

    def test_independent_path_survives_retraction(self):
        n = Node("n", "N", True)
        g = ProofGraph([n])
        g.add_root_support("n", "O", ("oA", 0), "r1")
        g.add_root_support("n", "C", ("oB", 0), "r2")
        newly = g.retract(("oA", 0))
        self.assertNotIn("n", newly)
        self.assertEqual(g.nodes["n"].status, "LIVE")
        self.assertIn("n", g.f_visible())

    def test_structural_child_survives_via_own_path(self):
        parent = Node("p", "N", True)
        child = Node("c", "N", False, usage_links={"p": "LIVE"})
        g = ProofGraph([parent, child])
        g.add_root_support("p", "O", ("oA", 0), "rp")
        g.add_root_support("c", "C", ("oB", 0), "rc")
        newly = g.retract(("oA", 0))
        self.assertIn("p", newly)
        self.assertNotIn("c", newly)          # keeps its own live path
        self.assertEqual(g.nodes["c"].status, "LIVE")
        self.assertIn("c", g.f_visible())

    def test_derived_path_dies_when_premise_retracted(self):
        p = Node("p", "N", True)
        c = Node("c", "G", True)
        g = ProofGraph([p, c])
        g.add_root_support("p", "O", ("oP", 0), "rp")
        g.add_derived_support("c", "AND_ELIMINATION", ["p"], ("oC", 0), "rd")
        self.assertIn("c", g.f_visible())     # premise p is visible -> derived path complete
        newly = g.retract(("oP", 0))
        self.assertIn("p", newly)
        self.assertIn("c", newly)             # its only path died with the premise
        self.assertEqual(g.nodes["c"].status, "SUPERSEDED")


class TestSomInvariant(unittest.TestCase):
    def test_healthy_graph_has_no_violations(self):
        g = ProofGraph([Node("m", "N", True)])
        g.add_root_support("m", "O", ("o", 0), "rm")
        self.assertEqual(g.som_violations(), [])

    def test_orphaned_asserted_fact_is_a_violation(self):
        n = Node("n", "N", True)
        g = ProofGraph([n])
        rec = g.add_root_support("n", "O", ("oA", 0), "r1")
        rec.status = "SUPERSEDED"             # its only path is dead, but the node is still LIVE
        self.assertEqual(g.som_violations(), ["n"])


if __name__ == "__main__":
    unittest.main()
