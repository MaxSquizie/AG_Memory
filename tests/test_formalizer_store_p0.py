# -*- coding: utf-8 -*-
"""P0 store contract tests — MemoryStore double + pure T6 decisions.

These verify PURE logic only (admission, plan\\E, terminal outcome) on the in-memory
double. They do NOT prove durability/atomicity/recovery-from-D; those are proven by
the AH adapter crash-stop runs (WP2.9). See store_interface docstring.
"""

import unittest

from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.store_interface import (
    AssertionStatus,
    CommitDecision,
    JournalRecord,
    MaterializationMarker,
    TerminalOutcome,
)
from ah.formalizer.t6_core import (
    PendingBatch,
    PlanOp,
    compute_plan_E,
    head_only_admission,
    select_terminal_outcome,
)


def _decision(batch_hash="h1", outcome=TerminalOutcome.APPLIED):
    marker = MaterializationMarker("obs1", 2)
    return CommitDecision(
        run_id="run-1", batch_hash=batch_hash, marker=marker, ops_digest="d", outcome=outcome
    )


class TestMemoryStoreJournal(unittest.TestCase):
    def test_append_assigns_monotonic_seq_and_head(self):
        s = MemoryStore()
        self.assertEqual(s.read_global_head(), 0)
        a = s.append_journal("observation", JournalRecord("observation", "r1", {"k": 1}))
        b = s.append_journal("resolution_log", JournalRecord("resolution_log", "r1", {"k": 2}))
        self.assertEqual((a, b), (1, 2))
        self.assertEqual(s.read_global_head(), 2)

    def test_scan_unprocessed_filters_and_orders(self):
        s = MemoryStore()
        for i in range(4):
            s.append_journal("observation", JournalRecord("observation", "r", {"i": i}))
        after = s.scan_unprocessed(1)  # seq > 1 -> records with i in {1,2,3}
        self.assertEqual([r.payload["i"] for r in after], [1, 2, 3])


class TestMemoryStoreCommit(unittest.TestCase):
    def test_commit_applies_ops_and_is_idempotent(self):
        from ah.formalizer.store_interface import StoreOp

        s = MemoryStore()
        ops = (StoreOp("ADD_ELEMENT", {"uid": "u1"}), StoreOp("ADD_LINK", {"uid": "u2"}))
        res = s.commit_transaction(ops, _decision().marker, _decision())
        self.assertEqual(res.applied_uids, ("u1", "u2"))
        self.assertTrue(s.has_uid("u1") and s.has_uid("u2"))

        again = s.commit_transaction(ops, _decision().marker, _decision(batch_hash="h1"))
        self.assertTrue(again.idempotent_noop)
        self.assertEqual(again.applied_uids, ())


class TestMemoryStoreRetraction(unittest.TestCase):
    def test_retract_transitions_without_deleting(self):
        from ah.formalizer.store_interface import StoreOp

        s = MemoryStore()
        s.commit_transaction((StoreOp("ADD_ELEMENT", {"uid": "a1"}),), _decision().marker, _decision())
        self.assertTrue(s.retract("a1", AssertionStatus.SUPERSEDED))
        self.assertEqual(s.status_of("a1"), AssertionStatus.SUPERSEDED)
        self.assertTrue(s.has_uid("a1"))  # not deleted

    def test_retract_unknown_id_returns_false(self):
        s = MemoryStore()
        self.assertFalse(s.retract("ghost", AssertionStatus.STALE))


class TestHeadOnlyAdmission(unittest.TestCase):
    def test_only_head_admitted_others_rejected(self):
        pending = [PendingBatch("b3", 30), PendingBatch("b1", 10), PendingBatch("b2", 20)]
        admitted, rejected = head_only_admission(pending)
        self.assertEqual(admitted.batch_id, "b1")
        self.assertEqual(rejected, ("b2", "b3"))

    def test_empty_pending(self):
        admitted, rejected = head_only_admission([])
        self.assertIsNone(admitted)
        self.assertEqual(rejected, ())


class TestPlanE(unittest.TestCase):
    def test_closure_common_preserved_nonadmitted_excluded(self):
        ops = [
            PlanOp("A"),                 # common? no; only included via closure of B
            PlanOp("B", deps=("A",)),    # admitted -> pulls in A
            PlanOp("C", in_E=False),     # common -> always kept
            PlanOp("D"),                 # E, not admitted, not a dep -> excluded
        ]
        plan = compute_plan_E(ops, ["B"])
        uids = [op.payload["uid"] for op in plan]
        self.assertIn("A", uids)   # transitive dep of admitted B
        self.assertIn("B", uids)   # admitted
        self.assertIn("C", uids)   # common preserved
        self.assertNotIn("D", uids)  # non-admitted E excluded

    def test_admitted_empty_keeps_only_common(self):
        ops = [PlanOp("A"), PlanOp("C", in_E=False)]
        uids = [op.payload["uid"] for op in compute_plan_E(ops, [])]
        self.assertEqual(uids, ["C"])


class TestTerminalOutcome(unittest.TestCase):
    def test_applied(self):
        self.assertIs(select_terminal_outcome(admitted_at_head=True, superseded=False), TerminalOutcome.APPLIED)

    def test_conflict_admission(self):
        self.assertIs(
            select_terminal_outcome(admitted_at_head=False, superseded=False),
            TerminalOutcome.REJECTED_CONFLICT_ADMISSION,
        )

    def test_stale_superseded(self):
        self.assertIs(
            select_terminal_outcome(admitted_at_head=True, superseded=True),
            TerminalOutcome.STALE_SUPERSEDED,
        )


if __name__ == "__main__":
    unittest.main()
