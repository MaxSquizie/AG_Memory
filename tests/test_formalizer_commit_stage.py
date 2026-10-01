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
from ah.formalizer.store_interface import TerminalOutcome
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


if __name__ == "__main__":
    unittest.main()
