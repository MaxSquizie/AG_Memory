# -*- coding: utf-8 -*-
"""Retraction protocol tests (V7 §8) — pure decision + atomic application on the double."""

import unittest

from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.retraction import EvidenceItem, RetractionProtocol, same_identity
from ah.formalizer.store_interface import (
    CommitDecision,
    MaterializationMarker,
    StoreOp,
    TerminalOutcome,
)


def _e(id_, tags, source=None, complete=True):
    return EvidenceItem(id=id_, tags=frozenset(tags), source_observation_id=source, complete=complete)


class TestRetractionDecision(unittest.TestCase):
    def test_independent_evidence_keeps_fact_alive(self):
        ev = [_e("E1", {"a"}, source="obs1"), _e("E2", {"b", "c"})]  # E2 independent channel
        out = RetractionProtocol().decide(ev, ["obs1"])
        self.assertTrue(out.survives)
        self.assertEqual(out.new_status.value, "LIVE")
        self.assertIn("E2", out.surviving_independent)

    def test_no_independent_evidence_supersedes(self):
        ev = [_e("E1", {"a"}, source="obs1"), _e("E3", {"d"}, source="obs1")]  # both from obs1
        out = RetractionProtocol().decide(ev, ["obs1"])
        self.assertFalse(out.survives)
        self.assertEqual(out.new_status.value, "SUPERSEDED")

    def test_duplicate_under_new_id_is_not_independent(self):
        # Same tags re-recorded under a new id must NOT manufacture independent support.
        ev = [_e("E1", {"a"}, source="obs1"), _e("E2-copy", {"a"})]  # E2-copy shares E1's exact tags
        out = RetractionProtocol().decide(ev, ["obs1"])
        self.assertFalse(out.survives)

    def test_partial_retraction_with_surviving_observation(self):
        ev = [_e("E1", {"a"}, source="obs1"), _e("E2", {"b"}, source="obs2")]
        out = RetractionProtocol().decide(ev, ["obs1"])  # obs2 untouched
        self.assertTrue(out.survives)
        self.assertIn("E2", out.surviving_independent)

    def test_incomplete_survivor_does_not_carry_fact(self):
        ev = [_e("E1", {"a"}, source="obs1"), _e("E2", {"b"}, complete=False)]
        out = RetractionProtocol().decide(ev, ["obs1"])
        self.assertFalse(out.survives)  # E2 incomplete -> cannot support alone

    def test_same_identity_is_exact_tag_equality(self):
        a = _e("x", {"a", "b"})
        b = _e("y", {"a", "b"})
        c = _e("z", {"a"})
        self.assertTrue(same_identity(a, b))
        self.assertFalse(same_identity(a, c))


class TestRetractionApplication(unittest.TestCase):
    def _materialize(self, s: MemoryStore, uid: str, batch_hash: str) -> None:
        # Materialize the assertion so retract can find it.
        s.commit_transaction(
            (StoreOp("ADD_ELEMENT", {"uid": uid}),),
            MaterializationMarker("o", 1),
            CommitDecision(run_id="r", batch_hash=batch_hash, marker=None, ops_digest="d",
                         outcome=TerminalOutcome.APPLIED),
        )

    def test_apply_supersedes_on_store(self):
        s = MemoryStore()
        self._materialize(s, "fact1", "h")
        proto = RetractionProtocol(store=s)
        ev = [_e("E1", {"a"}, source="obs1")]
        out = proto.apply("fact1", ev, ["obs1"])
        self.assertFalse(out.survives)
        self.assertEqual(s.status_of("fact1").value, "SUPERSEDED")

    def test_apply_survival_leaves_status_untouched(self):
        s = MemoryStore()
        self._materialize(s, "fact2", "h2")
        proto = RetractionProtocol(store=s)
        ev = [_e("E1", {"a"}, source="obs1"), _e("E2", {"b"})]
        out = proto.apply("fact2", ev, ["obs1"])  # E2 independent -> survives
        self.assertTrue(out.survives)
        self.assertIsNone(s.status_of("fact2"))  # no transition recorded


if __name__ == "__main__":
    unittest.main()
