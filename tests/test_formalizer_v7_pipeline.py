# -*- coding: utf-8 -*-
"""I01 — the single traceable production path (audit): real input flows through C -> T5 gate (+binding CAS)
-> T6 commit on a REAL file, instead of being converted to the legacy PerceptionResult and bypassing them.

Proven end-to-end against ACTUAL pipeline output (not fixtures), on a durable JournalChannel:
  * a RESOLVED single-value fragment with a FACT ground commits its fact durably through C+T5 (applied, APPLIED);
  * an UNRESOLVED [V1,V2] fragment materializes the observation record but asserts NO canonical fact;
  * a value grounded ONLY by M (interpretation-only) is refused by COND_5 -> no fact asserted (I12 through the real chain);
  * a foreign owner already holding the interpretation CAS-blocks this run -> INTEGRITY_ERROR, nothing committed;
  * re-committing the identical state across a restart is an idempotent no-op (same batch_hash).
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.store import AHStore

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.selection_protocol import load_decision_schema
from ah.formalizer.state import Decision, FrameCandidate, FormalizationState, Ground
from ah.formalizer.v7_pipeline import interpretation_run, run_from_state

SCHEMA = load_decision_schema()


def _adapter(path):
    return AHStoreAdapter(AHStore(), JournalChannel(path))


class TestV7ProductionPath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = str(Path(self._tmp.name) / "journal.log")

    # -- 1: RESOLVED single value with a FACT ground commits its fact through C+T5 ---- #
    def test_resolved_fact_commits_durable_through_c_t5(self):
        rep = interpretation_run(
            "У меня есть книга.", SCHEMA, FakeSelector.demo("augmented"), _adapter(self.log_path),
            InterpretationRunBinding(), context_facts=("Книга принадлежит мне.",), run_id="r-s3",
        )
        self.assertTrue(rep.binding_ok)
        self.assertEqual(rep.t5_eligibility, "OK")
        self.assertTrue(rep.applied)                       # durable write on the real file
        self.assertEqual(rep.terminal, "APPLIED")
        self.assertNotEqual(len(rep.committed_fragments), 0)   # a FACT was asserted (not observation-only)

    # -- 2: UNRESOLVED [V1,V2] materializes the observation but asserts NO fact ---- #
    def test_unresolved_materializes_observation_not_fact(self):
        rep = interpretation_run(
            "У вороны есть лапки.", SCHEMA, FakeSelector.demo("baseline"), _adapter(self.log_path),
            InterpretationRunBinding(), run_id="r-s1",
        )
        self.assertTrue(rep.applied)                       # observation + lexicon still commit durably (§7.2)
        self.assertEqual(rep.terminal, "APPLIED")
        self.assertEqual(rep.committed_fragments, ())      # no canonical fact for an unresolved fragment

    # -- 3: a value grounded ONLY by M is refused by COND_5 -> no fact (I12 through the real chain) ---- #
    def test_m_only_value_is_refused_by_cond5(self):
        state = FormalizationState(source_uid="u", interpretation_version=1, context_version=0, text="synthetic")
        state.frames.append(FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="s0:", participants=("a", "b")))
        # RESOLVED single value, but its ONLY ground is M (interpretation-only) -> never a fact.
        state.decisions["F1|predicate_value"] = Decision(
            slot_id="predicate_value", frame_id="F1", candidates=("V1", "V2"), selected=("V1",),
            outcome="RESOLVED", grounds=[Ground("M", "model judgment only", value="V1")],
        )
        rep = run_from_state(state, _adapter(self.log_path), InterpretationRunBinding(), schema=SCHEMA, run_id="r-m")
        self.assertEqual(rep.t5_eligibility, "OK")         # not an integrity/marker refusal...
        self.assertEqual(rep.committed_fragments, ())      # ...but the fact is NOT asserted (COND_5)

    # -- 4: a foreign owner already holding the interpretation CAS-blocks this run ---- #
    def test_foreign_owner_cas_blocks_commit(self):
        binding = InterpretationRunBinding()
        self.assertTrue(binding.acquire("other-run", "obs-fixed", 1))   # someone else owns it first
        rep = interpretation_run(
            "У меня есть книга.", SCHEMA, FakeSelector.demo("augmented"), _adapter(self.log_path),
            binding, context_facts=("Книга принадлежит мне.",), run_id="r-me", observation_id="obs-fixed",
        )
        self.assertFalse(rep.binding_ok)
        self.assertEqual(rep.t5_eligibility, "INTEGRITY_ERROR")
        self.assertFalse(rep.applied)                     # nothing was committed by the blocked run

    # -- 5: re-committing the identical state across a restart is an idempotent no-op ---- #
    def test_idempotent_recommit_across_restart(self):
        binding = InterpretationRunBinding()
        first = interpretation_run(
            "У меня есть книгу.", SCHEMA, FakeSelector.demo("augmented"), _adapter(self.log_path),
            binding, context_facts=("Книга принадлежит мне.",), run_id="r-s3",
        )
        self.assertTrue(first.applied)

        # Restart: a fresh adapter over the SAME durable file; same owner re-claims (idempotent CAS).
        second = interpretation_run(
            "У меня есть книгу.", SCHEMA, FakeSelector.demo("augmented"), _adapter(self.log_path),
            binding, context_facts=("Книга принадлежит мне.",), run_id="r-s3",
        )
        self.assertFalse(second.applied)                  # idempotent no-op across restart
        self.assertEqual(first.batch_hash, second.batch_hash)


if __name__ == "__main__":
    unittest.main()
