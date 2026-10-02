# -*- coding: utf-8 -*-
"""WP2.3 — T6 claim + admission tests (V7 §7.3).

Proves the single-writer gate on a pure module: a smaller unprocessed seq -> PENDING_ADMISSION_ORDER with nothing
written; an already-terminal repeat is idempotent; a matching COMMITTED marker completes idempotently while a
mismatching one is INTEGRITY_ERROR (terminal REJECTED_COMMIT_ELIGIBILITY); a foreign run_id without a marker is
REJECTED_COMMIT_ELIGIBILITY without AH change; the clean global head is admitted. STALE_SUPERSEDED is created only
by mark_stale, and drain_order yields ascending unprocessed seqs skipping terminal records.
"""

import unittest

from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.t6_admission import JournalRecord, claim, drain_order, mark_stale


def rec(seq, run="R1", obs="obs1", ver=0, hash="h", terminal=None):
    return JournalRecord(seq=seq, batch_id=f"b{seq}", run_id=run, observation_id=obs, version=ver,
                        batch_hash=hash, terminal=terminal)


class TestClaim(unittest.TestCase):
    def test_smaller_unprocessed_seq_is_pending(self):
        r = claim(rec(5), [rec(1), rec(5)], {}, InterpretationRunBinding())
        self.assertEqual(r.outcome, "PENDING_ADMISSION_ORDER")
        self.assertEqual(r.blocking_seqs, (1,))
        self.assertIsNone(r.terminal_status)  # nothing written

    def test_terminal_repeat_is_idempotent(self):
        r = claim(rec(1, terminal="APPLIED"), [rec(1, terminal="APPLIED")], {}, InterpretationRunBinding())
        self.assertEqual(r.outcome, "IDEMPOTENT_NOOP")
        self.assertEqual(r.terminal_status, "APPLIED")

    def test_matching_marker_completes_idempotently(self):
        binding = InterpretationRunBinding()
        r = claim(rec(1), [rec(1)], {("obs1", 0): "h"}, binding)
        self.assertEqual(r.outcome, "IDEMPOTENT_NOOP")

    def test_mismatching_marker_is_integrity_error(self):
        r = claim(rec(1, hash="h"), [rec(1, hash="h")], {("obs1", 0): "OTHER"}, InterpretationRunBinding())
        self.assertEqual(r.outcome, "INTEGRITY_ERROR")
        self.assertEqual(r.terminal_status, "REJECTED_COMMIT_ELIGIBILITY")

    def test_foreign_owner_without_marker_is_rejected(self):
        binding = InterpretationRunBinding()
        binding.acquire("OTHER", "obs1", 0)
        r = claim(rec(1), [rec(1)], {}, binding)
        self.assertEqual(r.outcome, "REJECTED_COMMIT_ELIGIBILITY")
        self.assertEqual(r.terminal_status, "REJECTED_COMMIT_ELIGIBILITY")

    def test_clean_global_head_is_admitted(self):
        r = claim(rec(1), [rec(1)], {}, InterpretationRunBinding())
        self.assertEqual(r.outcome, "ADMIT")


class TestStaleAndDrain(unittest.TestCase):
    def test_mark_stale_only_when_unprocessed(self):
        stale = mark_stale(rec(1))
        self.assertEqual(stale.terminal, "STALE_SUPERSEDED")
        # already-terminal records are not re-marked
        same = mark_stale(rec(1, terminal="APPLIED"))
        self.assertEqual(same.terminal, "APPLIED")

    def test_drain_order_ascending_and_skips_terminal(self):
        recs = [rec(3), rec(1), rec(2, terminal="APPLIED")]
        self.assertEqual(drain_order(recs), (1, 3))


if __name__ == "__main__":
    unittest.main()
