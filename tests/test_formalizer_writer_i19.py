# -*- coding: utf-8 -*-
"""I19 — the concrete AH writer preserves types and attaches canonical truth-grounds.

The audit's I19 names two defects in the real graph writer (graph_ops handlers over a live AHCore):
  * an entity actant is materialized as S instead of M (type loss);
  * asserted facts are written with EMPTY supports (no canonical O/C/W ground).

Both fixes are additive/opt-in, so existing string-actant ops behave exactly as before. These tests drive the
handlers on a real AHCore and prove: entity actants become M, lexical actants stay S, an op carrying ``supports``
gets a canonical SupportRecord attached (relation_id encodes the §7.4 ground kind), and an op without supports
attaches nothing (regression).
"""

import unittest

from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.formalizer.graph_ops import handle_add_hypernode
from ah.model import Domain, Hypernode, RefKind


def _fact_node(core) -> Hypernode:
    nodes = [e for e in core.store._state.domains[Domain.C].values() if isinstance(e, Hypernode)]
    assert nodes, "no hypernode materialized"
    return nodes[-1]


class TestI19WriterTypesAndSupports(unittest.TestCase):
    def setUp(self):
        self.core = AHCore(AHStore())

    def test_entity_actant_is_materialized_as_m_not_s(self):
        self.core.add_hypernode  # noqa: B018 (attribute presence sanity)
        handle_add_hypernode(self.core, {
            "domain": "C", "predicate_form": "love", "roles": ["SUBJECT", "OBJECT"],
            "actants": {"SUBJECT": {"form": "bird", "kind": "M"}, "OBJECT": "worm"},
        })
        hn = _fact_node(self.core)
        subj, obj = list(hn.actants.values())[0], list(hn.actants.values())[1]
        self.assertEqual(self.core.store.kind_of(subj.uid), RefKind.M)  # entity preserved as M (was S before)
        self.assertEqual(self.core.store.kind_of(obj.uid), RefKind.S)   # lexical actant stays S

    def test_plain_string_actant_still_resolves_to_s_regression(self):
        handle_add_hypernode(self.core, {
            "domain": "C", "predicate_form": "love", "roles": ["SUBJECT"],
            "actants": {"SUBJECT": "bird"},  # plain string -> lexical S (unchanged default)
        })
        hn = _fact_node(self.core)
        subj = list(hn.actants.values())[0]
        self.assertEqual(self.core.store.kind_of(subj.uid), RefKind.S)

    def test_op_with_supports_attaches_canonical_ground_record(self):
        handle_add_hypernode(self.core, {
            "domain": "C", "predicate_form": "love", "roles": ["SUBJECT"],
            "actants": {"SUBJECT": "bird"},
            "supports": ["O"],  # directly observed fact -> O ground
        })
        hn = _fact_node(self.core)
        supps = self.core.resolve_supports(self.core.ref(hn.uid))
        self.assertEqual(len(supps), 1)
        self.assertEqual(supps[0].relation_id, "GROUND:O")

    def test_op_without_supports_attaches_nothing_regression(self):
        handle_add_hypernode(self.core, {
            "domain": "C", "predicate_form": "love", "roles": ["SUBJECT"],
            "actants": {"SUBJECT": "bird"},  # no "supports" key -> untouched
        })
        hn = _fact_node(self.core)
        self.assertEqual(self.core.resolve_supports(self.core.ref(hn.uid)), ())

    def test_multiple_ground_types_each_get_a_record(self):
        handle_add_hypernode(self.core, {
            "domain": "C", "predicate_form": "love", "roles": ["SUBJECT"],
            "actants": {"SUBJECT": "bird"},
            "supports": ["O", "W"],  # observed + world-grounded -> two canonical records
        })
        hn = _fact_node(self.core)
        rels = sorted(s.relation_id for s in self.core.resolve_supports(self.core.ref(hn.uid)))
        self.assertEqual(rels, ["GROUND:O", "GROUND:W"])


if __name__ == "__main__":
    unittest.main()
