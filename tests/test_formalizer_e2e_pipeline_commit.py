# -*- coding: utf-8 -*-
"""End-to-end vertical integration: Phase 1 pipeline -> T5/T6 commit on a REAL file.

The existing commit-stage tests feed ``commit()`` a hand-built state. This module closes the missing
proof that the ACTUAL output of :func:`ah.formalizer.pipeline.run` (T0-T4, with real T4 outcomes)
commits durably through the same vertical path:

    run(text, schema, selector) -> FormalizationState --assemble_ir--> CandidateIR
        -> commit(state, AHStoreAdapter(AHStore(), JournalChannel(file)), run_id=...)

Assertions target the durable contracts on REAL pipeline output (not a fixture):
  * a RESOLVED and an UNRESOLVED sentence both materialize their observation + lexicon (applied=True,
    terminal APPLIED, a global head is written through) — §7.2: the observation record is a COMMON op;
  * re-committing the identical state across a restart is an idempotent no-op (same batch_hash);
  * a complete commit is NOT double-restored by recovery;
  * two distinct sentences are independent commits (distinct observation_id / batch_hash, no cross-talk).

The semantic value binding lives in the decision layer (T4 outcome), not re-materialized as a distinct
store element by ``commit()`` — so these tests assert the durable vertical path, while Phase 1 tests
already pin the RESOLVED/UNRESOLVED semantics.
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.store import AHStore

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.commit_stage import commit
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.memory_store import MemoryStore  # noqa: F401 (spine presence)
from ah.formalizer.pipeline import run
from ah.formalizer.selection_protocol import load_decision_schema

SCHEMA = load_decision_schema()


def _run(text, *, mode="baseline", fact=None):
    sel = FakeSelector.demo(mode)
    return run(text, SCHEMA, sel, context_facts=(fact,) if fact else ())


class TestPipelineCommitOnRealFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"

    def _adapter(self):
        return AHStoreAdapter(AHStore(), JournalChannel(self.log_path))

    def test_resolved_sentence_commits_durable_on_disk(self):
        st = _run("У меня есть книга.")  # S3 -> RESOLVED V1
        a1 = self._adapter()
        rep = commit(st, a1, run_id="r-s3")
        self.assertTrue(rep.admitted_at_head)
        self.assertTrue(rep.applied)
        self.assertEqual(rep.terminal.name, "APPLIED")
        self.assertIsNotNone(a1.read_global_head())  # the D (commit decision) was written through

    def test_unresolved_sentence_still_materializes_observation(self):
        # §7.2: a non-RESOLVED fragment yields an ObservationRecord WITHOUT a canonical fact, but the
        # observation + lexicon are COMMON ops that still commit durably.
        st = _run("У вороны есть лапки.")  # S1 baseline -> UNRESOLVED [V1,V2]
        a1 = self._adapter()
        rep = commit(st, a1, run_id="r-s1")
        self.assertTrue(rep.applied)
        self.assertEqual(rep.terminal.name, "APPLIED")

    def test_recommit_is_idempotent_across_restart(self):
        st = _run("У меня есть книга.")
        a1 = self._adapter()
        first = commit(st, a1, run_id="r-s3")
        self.assertTrue(first.applied)

        # Restart: a fresh adapter over the SAME file; re-committing the identical state is a no-op.
        a2 = AHStoreAdapter(AHStore(), JournalChannel(self.log_path))
        again = commit(st, a2, run_id="r-s3")
        self.assertFalse(again.applied)  # idempotent across restart (same batch_hash from real IR)

    def test_complete_commit_not_double_restored_after_restart(self):
        st = _run("У меня есть книга.")
        commit(st, self._adapter(), run_id="r-s3")  # D + terminal both on disk

        a2 = AHStoreAdapter(AHStore(), JournalChannel(self.log_path))  # restart from the SAME file
        report = a2.recover_from_head()
        self.assertFalse(report.re_admitted)
        self.assertEqual(report.recovered, ())  # terminal present -> NOT double-restored

    def test_distinct_sentences_are_independent_commits(self):
        s3 = _run("У меня есть книга.")          # RESOLVED V1
        s1 = _run("У вороны есть лапки.")        # UNRESOLVED [V1,V2]
        a1 = self._adapter()
        r3 = commit(s3, a1, run_id="r-s3")
        r1 = commit(s1, a1, run_id="r-s1")
        # Different text -> different observation identity -> independent batch hashes.
        self.assertNotEqual(r3.batch_hash, r1.batch_hash)
        self.assertTrue(r3.applied and r1.applied)


if __name__ == "__main__":
    unittest.main()
