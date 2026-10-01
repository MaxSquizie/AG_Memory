# -*- coding: utf-8 -*-
"""AH adapter tests — R1-critical store properties against a REAL file.

These run the :class:`AHStoreAdapter` over a real :class:`AHStore` and a real on-disk
:class:`JournalChannel`, so they exercise durability/idempotency/recovery-from-D that an
in-memory double cannot. (Full op→graph mutation handlers are a P2 extension point; here we
verify the store-level guarantees.)
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.store import AHStore

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.store_interface import (
    AssertionStatus,
    CommitDecision,
    MaterializationMarker,
    StoreOp,
    TerminalOutcome,
)


def _decision(batch_hash="h1", outcome=TerminalOutcome.APPLIED):
    return CommitDecision(
        run_id="run-1", batch_hash=batch_hash,
        marker=MaterializationMarker("obs1", 2), ops_digest="d", outcome=outcome,
    )


class TestAHAdapter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"

    def _adapter(self):
        return AHStoreAdapter(AHStore(), JournalChannel(self.log_path))

    def test_commit_is_durable_and_idempotent(self):
        a = self._adapter()
        ops = (StoreOp("ADD_ELEMENT", {"uid": "u1"}), StoreOp("ADD_LINK", {"uid": "u2"}))
        res = a.commit_transaction(ops, _decision().marker, _decision())
        self.assertEqual(res.applied_uids, ("u1", "u2"))

        # Reopen from the same file: same batch_hash is an idempotent no-op.
        b = self._adapter()
        again = b.commit_transaction(ops, _decision().marker, _decision())
        self.assertTrue(again.idempotent_noop)
        self.assertEqual(again.applied_uids, ())

    def test_recover_from_d_without_readmission(self):
        a = self._adapter()
        ops = (StoreOp("ADD_ELEMENT", {"uid": "u1"}),)
        a.commit_transaction(ops, _decision().marker, _decision())  # committed D, no terminal yet

        b = self._adapter()  # fresh process over the same durable log
        report = b.recover_from_head()
        self.assertFalse(report.re_admitted)
        self.assertIn(("batch:h1", TerminalOutcome.APPLIED), report.recovered)

    def test_recovered_batch_not_double_restored_after_terminal(self):
        a = self._adapter()
        ops = (StoreOp("ADD_ELEMENT", {"uid": "u1"}),)
        a.commit_transaction(ops, _decision().marker, _decision())
        a.append_terminal("batch:h1", TerminalOutcome.APPLIED)  # crash happened after terminal

        b = self._adapter()
        report = b.recover_from_head()
        self.assertEqual(report.recovered, ())  # already APPLIED -> nothing to restore

    def test_retract_durable_and_unknown_false(self):
        a = self._adapter()
        ops = (StoreOp("ADD_ELEMENT", {"uid": "u1"}),)
        a.commit_transaction(ops, _decision().marker, _decision())
        # u1 is not in the fresh store here, but the commit unit marks it known via status after terminal:
        a.append_terminal("u1", TerminalOutcome.APPLIED)
        self.assertTrue(a.retract("u1", AssertionStatus.SUPERSEDED))
        self.assertEqual(a.status_of("u1"), AssertionStatus.SUPERSEDED)

        b = self._adapter()  # reopen: retraction record is durable
        recs = [r.payload for r in b.scan_unprocessed(0)]
        self.assertTrue(any(p.get("kind") == "retract" and p["assertion_id"] == "u1" for p in recs))

    def test_retract_unknown_returns_false(self):
        a = self._adapter()
        self.assertFalse(a.retract("ghost", AssertionStatus.STALE))


if __name__ == "__main__":
    unittest.main()
