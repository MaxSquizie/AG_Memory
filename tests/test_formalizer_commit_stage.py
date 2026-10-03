# -*- coding: utf-8 -*-
"""Commit-stage tests — T5/T6 wiring of IR + admission + plan\\E into a durable transaction.

Fast cases run on the in-memory double; one case runs against a REAL file (AHStoreAdapter over
an AHStore + JournalChannel) to prove crash-stop durability and idempotency at the store level.
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.store import AHStore

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.commit_stage import commit
from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.state import FrameCandidate, FormalizationState, TokenEvidence
from ah.formalizer.store_interface import CommitDecision, MaterializationMarker, StoreOp, TerminalOutcome
from ah.formalizer.t6_core import PendingBatch


def _state() -> FormalizationState:
    st = FormalizationState.new("Ворона имеет перья")
    for span in ("Ворона", "имеет", "перья"):
        st.evidence.append(TokenEvidence(span=span))
    st.frames.append(FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="имеет",
                                   participants=("Ворона", "перья")))
    return st


class TestMemoryCommit(unittest.TestCase):
    def test_single_run_applies(self):
        s = MemoryStore()
        rep = commit(_state(), s, run_id="r1")
        self.assertTrue(rep.admitted_at_head)
        self.assertTrue(rep.applied)
        self.assertEqual(rep.terminal, TerminalOutcome.APPLIED)
        self.assertGreaterEqual(rep.n_ops, 3)   # observation + frame + graph

    def test_non_head_run_rejected_and_writes_only_common(self):
        s = MemoryStore()
        pending = [PendingBatch(batch_id="aaa", seq=0)]
        rep = commit(_state(), s, run_id="zzz", pending=pending)  # "aaa" < "zzz" -> not at head
        self.assertFalse(rep.admitted_at_head)
        self.assertEqual(rep.terminal, TerminalOutcome.REJECTED_CONFLICT_ADMISSION)
        self.assertEqual(rep.n_ops, 1)           # only the common observation op survives

    def test_idempotency_no_double_write(self):
        s = MemoryStore()
        first = commit(_state(), s, run_id="r1")
        second = commit(_state(), s, run_id="r1")   # same batch_hash
        self.assertTrue(first.applied)
        self.assertFalse(second.applied)           # duplicate rejected by the store

    def test_superseded_terminal(self):
        s = MemoryStore()
        rep = commit(_state(), s, run_id="r1", superseded=True)
        self.assertEqual(rep.terminal, TerminalOutcome.STALE_SUPERSEDED)


class TestCrashStopCommit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"

    def _adapter(self):
        return AHStoreAdapter(AHStore(), JournalChannel(self.log_path))

    def test_commit_is_durable_and_idempotent_on_disk(self):
        a1 = self._adapter()
        rep = commit(_state(), a1, run_id="r1")
        self.assertTrue(rep.applied)
        self.assertIsNotNone(a1.read_global_head())   # a D (terminal) was written through

        # Restart: a fresh adapter over the SAME file recovers the head and rejects the dup.
        a2 = AHStoreAdapter(AHStore(), JournalChannel(self.log_path))
        self.assertIsNotNone(a2.read_global_head())
        again = commit(_state(), a2, run_id="r1")
        self.assertFalse(again.applied)              # idempotent across restart

    def test_complete_commit_not_double_restored_after_restart(self):
        """WP0.5 — a COMPLETE vertical commit (D + terminal both on disk) must NOT be re-surfaced by recovery.

        Regression for the run_id-vs-batch:<hash> key mismatch: the terminal is now keyed by the batch identity
        that recover_from_head looks up, so an already-APPLIED batch stays restored exactly once."""
        a1 = self._adapter()
        commit(_state(), a1, run_id="r1")            # writes D + the batch-keyed terminal to disk

        a2 = AHStoreAdapter(AHStore(), JournalChannel(self.log_path))  # restart from the SAME file
        report = a2.recover_from_head()
        self.assertFalse(report.re_admitted)
        self.assertEqual(report.recovered, ())       # terminal present -> NOT double-restored

    def test_crash_before_terminal_recovers_without_readmission(self):
        """WP0.5 — crash AFTER the commit unit D but BEFORE the terminal: recovery restores the decided APPLIED
        batch from D WITHOUT re-running admission (re_admitted stays False)."""
        a1 = self._adapter()
        decision = CommitDecision(run_id="r9", batch_hash="hX",
                                 marker=MaterializationMarker("obs1", 2), ops_digest="d",
                                 outcome=TerminalOutcome.APPLIED)
        a1.commit_transaction((StoreOp("ADD_ELEMENT", {"uid": "u1"}),), decision.marker, decision)  # D only
        # (no append_terminal -> the crash happened before the terminal was durably written)

        a2 = AHStoreAdapter(AHStore(), JournalChannel(self.log_path))
        report = a2.recover_from_head()
        self.assertFalse(report.re_admitted)
        self.assertIn(("batch:hX", TerminalOutcome.APPLIED), report.recovered)  # restored from D, not re-admitted


class TestGraphMaterialization(unittest.TestCase):
    """Slice #3: the commit seam materializes admitted semantic graphs into a REAL store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"

    def _adapter(self):
        from ah.core import AHCore
        from ah.formalizer.graph_ops import register_graph_handlers

        # Graph ops are applied only when the adapter is given a live core (see AHStoreAdapter._apply_ops).
        self._core = AHCore()
        a = AHStoreAdapter(self._core.store, JournalChannel(self.log_path), core=self._core)
        register_graph_handlers(a)
        return a

    def _predicate_templates(self, st) -> tuple:
        from ah.formalizer.composition import _lemma_of

        store = self._core.store
        lemma = _lemma_of(st.evidence, "имеет")
        sym = store.find_symbol_by_form(lemma)
        return store.find_templates_by_predicate(sym.uid) if sym else ()

    def test_admitted_commit_materializes_graph_in_real_store(self):
        st = _state()
        a = self._adapter()
        rep = commit(st, a, run_id="r1")
        self.assertTrue(rep.applied)
        templates = self._predicate_templates(st)
        self.assertTrue(templates, "an admitted commit must materialize its semantic graph's template in C")

    def test_non_head_run_writes_no_graph_facts(self):
        st = _state()
        a = self._adapter()
        rep = commit(st, a, run_id="zzz", pending=[PendingBatch(batch_id="aaa", seq=0)])
        self.assertFalse(rep.admitted_at_head)
        self.assertEqual(
            self._predicate_templates(st), (), "a non-head run writes no version-specific graph facts"
        )


if __name__ == "__main__":
    unittest.main()
