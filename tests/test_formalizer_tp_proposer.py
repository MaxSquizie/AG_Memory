# -*- coding: utf-8 -*-
"""WP1.3 — TP protocol + deterministic validator tests (V7 §4.5).

Proves each invariant (a)-(f) in isolation, the budget pre-check, and a FakeProposer round-trip that
mirrors how the real backend will be exercised through ProviderCallLog.
"""

import unittest

from ah.formalizer.fake_selector import FakeProposer, ProviderUnavailableError
from ah.formalizer.selection_protocol import ProtocolError
from ah.formalizer.tp_proposer import (
    Hypothesis, StructureProposalRequest, TEdge, TNode, budget_precheck, parse_and_validate,
    validate_structure_reply,
)


def _req(**kw):
    base = dict(
        request_id="r1", structural_hash_pre="h0", source_spans=("s0:s3", "s2:s3"),
        allowed_node_kinds=frozenset({"CLAUSE", "ARG"}), allowed_edge_kinds=frozenset({"GOVERNS"}),
    )
    base.update(kw)
    return StructureProposalRequest(**base)


def _valid_reply():
    from ah.formalizer.tp_proposer import StructureProposalReply
    hyp = Hypothesis(
        local_id="H1",
        nodes=(TNode("CLAUSE", ("s0:s3",)), TNode("ARG", ("s2:s3",))),
        edges=(TEdge("GOVERNS", 0, 1, role_id="SURFACE_ARG"),),
    )
    return StructureProposalReply(hypotheses=(hyp,))


class TestValidator(unittest.TestCase):
    def test_valid_reply_accepted(self):
        self.assertEqual(len(validate_structure_reply(_req(), _valid_reply())), 1)

    def test_b_anchor_outside_region_rejected(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        hyp = Hypothesis("H1", (TNode("CLAUSE", ("s9:s9",)),))
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_c_node_kind_not_allowed_rejected(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        hyp = Hypothesis("H1", (TNode("MYSTERY", ("s0:s3",)),))
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_c_edge_kind_not_allowed_rejected(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        hyp = Hypothesis("H1", (TNode("CLAUSE", ("s0:s3",)), TNode("ARG", ("s2:s3",))),
                         edges=(TEdge("MAGIC", 0, 1),))
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_b_edge_endpoint_out_of_range_rejected(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        hyp = Hypothesis("H1", (TNode("CLAUSE", ("s0:s3",)),), edges=(TEdge("GOVERNS", 0, 5),))
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_a_invented_role_rejected(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        hyp = Hypothesis("H1", (TNode("CLAUSE", ("s0:s3",)), TNode("ARG", ("s2:s3",))),
                         edges=(TEdge("GOVERNS", 0, 1, role_id="AGENT"),))  # AGENT not registered here
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_d_surface_arg_must_anchor_proper_subregion(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        # SURFACE_ARG target anchors the ENTIRE bounded region -> not a proper subset.
        hyp = Hypothesis("H1", (TNode("CLAUSE", ("s0:s3",)), TNode("ARG", ("s0:s3", "s2:s3"))),
                         edges=(TEdge("GOVERNS", 0, 1, role_id="SURFACE_ARG"),))
        with self.assertRaises(ProtocolError):
            validate_structure_reply(_req(), StructureProposalReply(hypotheses=(hyp,)))

    def test_e_budget_precheck_blocks_call(self):
        req = _req(budget_ok=False)
        with self.assertRaises(ProtocolError):
            validate_structure_reply(req, _valid_reply())


class TestMissAndBudget(unittest.TestCase):
    def test_abstain_is_explicit_miss_not_ambiguous(self):
        from ah.formalizer.tp_proposer import StructureProposalReply
        self.assertEqual(validate_structure_reply(_req(), StructureProposalReply(abstain=True)), [])

    def test_missing_raw_is_explicit_miss(self):
        self.assertEqual(parse_and_validate(_req(), None), [])

    def test_budget_precheck(self):
        class B:
            llm_exhausted = True
        self.assertFalse(budget_precheck(B()))
        self.assertTrue(budget_precheck(object()))  # no attribute -> not exhausted


class TestFakeProposerRoundTrip(unittest.TestCase):
    def test_demo_reply_validates_end_to_end(self):
        req = _req(request_id="tp_demo_1")
        raw = FakeProposer.demo().propose(req)
        hyps = parse_and_validate(req, raw)
        self.assertEqual(len(hyps), 1)
        self.assertEqual(hyps[0].edges[0].role_id, "SURFACE_ARG")

    def test_unscripted_request_abstains(self):
        self.assertIsNone(FakeProposer.demo().propose(_req(request_id="nope")))

    def test_provider_unavailable_raises(self):
        p = FakeProposer({"r1": "PROVIDER_UNAVAILABLE"})
        with self.assertRaises(ProviderUnavailableError):
            p.propose(_req())


if __name__ == "__main__":
    unittest.main()
