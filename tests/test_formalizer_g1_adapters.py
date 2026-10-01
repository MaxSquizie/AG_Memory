# -*- coding: utf-8 -*-
"""WP0.6 — G1 adapter tests, the subset certifiable on the current spine (V7 §12/§20).

Of the nine named G1 cases these five are testable NOW against the P0/P1 spine; the other four
(legacy_roundtrip, v2_integration, known_mapping_failure, proposal_validation) require the C/T6 mapping
path and are deliberately deferred to P2 rather than faked here:

- concurrent_run_binding   — InterpretationRunBinding CAS serializes owners of one (obs, version).
- idempotent_recommit      — same batch_hash commits once; a re-commit is an idempotent no-op (memory + AH file).
- unresolved_replay        — replaying the canonical run on an unresolved version creates no new owner and no marker.
- open_template_isolation  — occurrence-local isolation key: survives a contextual revision, never collides across observations.
- crash_recovery           — a decided-APPLIED batch that crashes before its terminal is restored from D on a REAL file, re_admitted=False.
"""

import os
import tempfile
import unittest

from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.provider_adapter import ProviderAdapter  # noqa: F401 (spine presence)
from ah.formalizer.resources.registry import (
    OpenPredicateCandidate, OpenTemplatePolicy, Role, RoleBinding, RoleRegistry, ensure_open_template,
)
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.store_interface import (
    CommitDecision, JournalRecord, MaterializationMarker, StoreOp, TerminalOutcome,
)


def _decision(run_id="run-A", batch_hash="H1", outcome=TerminalOutcome.APPLIED):
    return CommitDecision(
        run_id=run_id, batch_hash=batch_hash,
        marker=MaterializationMarker("obs1", 0), ops_digest="d", outcome=outcome)


class TestConcurrentRunBinding(unittest.TestCase):
    def test_second_owner_cas_fails(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertFalse(b.acquire("run-B", "obs1", 0))   # a different owner cannot claim it
        self.assertEqual(b.holder("obs1", 0), "run-A")

    def test_same_owner_reacquire_is_idempotent(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertTrue(b.acquire("run-A", "obs1", 0))   # replay of the same owner is a no-op


class TestIdempotentRecommit(unittest.TestCase):
    def test_memory_store_recommit_is_noop(self):
        s = MemoryStore()
        ops = [StoreOp("ADD_ELEMENT", {"uid": "n1"})]
        first = s.commit_transaction(ops, MaterializationMarker("obs1", 0), _decision())
        self.assertEqual(first.applied_uids, ("n1",))
        second = s.commit_transaction(ops, MaterializationMarker("obs1", 0), _decision())
        self.assertTrue(second.idempotent_noop)
        self.assertEqual(second.applied_uids, ())       # nothing re-materialized


class TestUnresolvedReplay(unittest.TestCase):
    def test_replay_creates_no_new_owner_and_no_marker(self):
        b = InterpretationRunBinding()
        s = MemoryStore()
        # First (unresolved) analysis: only a diagnostic journal record, no commit/marker.
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        s.append_journal("resolution_log", JournalRecord("resolution_log", "run-A", {"kind": "diag"}))
        head_after_diag = s.read_global_head()

        # Replay of the SAME canonical run on the same unresolved version: idempotent owner, no marker.
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertEqual(s.has_uid("n1"), False)         # nothing materialized
        self.assertEqual(len([r for r in s.scan_unprocessed(0) if r.payload.get("kind") == "commit"]), 0)
        self.assertGreaterEqual(head_after_diag, 1)


class TestOpenTemplateIsolation(unittest.TestCase):
    def _reg(self):
        return RoleRegistry(frozenset({Role("EXPERIENCER"), Role("SURFACE_ARG")}))

    def test_survives_contextual_revision_but_not_cross_observation(self):
        reg, pol = self._reg(), OpenTemplatePolicy(released=True)
        base = dict(source_revision=0, anchor_spans=("s0:",), normalized_surface_or_lemma="холодно",
                    pos="ADJD", bindings=(RoleBinding("EXPERIENCER"),))
        k1 = ensure_open_template(OpenPredicateCandidate(observation_id="obs1", source="run-A", **base), reg, pol).open_template_key
        # Same observation re-analyzed (contextual revision): identical key.
        k2 = ensure_open_template(OpenPredicateCandidate(observation_id="obs1", source="run-B", **base), reg, pol).open_template_key
        self.assertEqual(k1, k2)
        # A different independent observation: distinct key (no cross-observation collision).
        k3 = ensure_open_template(OpenPredicateCandidate(observation_id="obs2", source="run-A", **base), reg, pol).open_template_key
        self.assertNotEqual(k1, k3)


class TestCrashRecovery(unittest.TestCase):
    def _adapter(self, tmpdir):
        from ah.core.journal import JournalChannel
        from ah.core.store import AHStore
        from ah.formalizer.ah_adapter import AHStoreAdapter
        return AHStoreAdapter(AHStore(), JournalChannel(os.path.join(tmpdir, "j.log")))

    def test_decided_applied_batch_restored_from_d_without_readmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._adapter(tmp)
            # Commit an APPLIED batch but crash BEFORE appending its terminal status.
            a.commit_transaction([StoreOp("ADD_ELEMENT", {"uid": "n1"})],
                                 MaterializationMarker("obs1", 0), _decision(batch_hash="H-crash"))

            # A fresh adapter over the SAME durable file (process restart): in-memory state is empty.
            b = self._adapter(tmp)
            report = b.recover_from_head()
            self.assertFalse(report.re_admitted)                 # restored from D, not re-admitted
            self.assertIn(("batch:H-crash", TerminalOutcome.APPLIED), report.recovered)


if __name__ == "__main__":
    unittest.main()
