# -*- coding: utf-8 -*-
"""WP2.2 — T5 batch + journal tests (V7 §7.2).

Proves the commit gate on a pure module: each of the five conditions (i–v) fails with its own durable
resolution_log entry naming the condition number; non-RESOLVED outcomes yield an ObservationRecord without a
canonical fact; known-mapping refusal and candidate-source exhaustion are journaled durably; commit eligibility
is enforced via InterpretationRunBinding (foreign owner -> INTEGRITY_ERROR, investigation-only -> audit only);
a pre-existing marker is an early refusal not journaled; and re-running the same batch_hash is idempotent.
"""

import unittest

from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.t5_batch import FragmentT5Input, t5_batch


def ok(**kw):
    base = dict(fragment_id="f1", outcome="RESOLVED", generation_complete=True, pending_reads=(),
                dependencies_resolved=True, integrity_ok=True, truth_grounds=("O",))
    base.update(kw)
    return FragmentT5Input(**base)


def run(frags, **kw):
    kw.setdefault("run_id", "R1")
    kw.setdefault("observation_id", "obs1")
    kw.setdefault("version", 0)
    kw.setdefault("binding", InterpretationRunBinding())
    return t5_batch(frags, **kw)


class TestFiveConditions(unittest.TestCase):
    def test_all_true_is_committable(self):
        r = run([ok()])
        self.assertEqual(r.eligibility, "OK")
        self.assertEqual(r.committed_fragments, ("f1",))
        self.assertEqual(r.journal_entries, ())

    def test_each_condition_fails_with_its_number(self):
        cases = [
            (dict(generation_complete=False), "COND_1"),
            (dict(pending_reads=("r",)), "COND_2"),
            (dict(dependencies_resolved=False), "COND_3"),
            (dict(integrity_ok=False), "COND_4"),
            (dict(truth_grounds=()), "COND_5"),
        ]
        for overrides, expected in cases:
            r = run([ok(**overrides)])
            self.assertEqual(r.committed_fragments, (), f"{expected} should not commit")
            entry = [e for e in r.journal_entries if e.get("fragment_id") == "f1"][0]
            self.assertEqual(entry["kind"], "resolution_log")
            self.assertEqual(entry["condition"], expected)


class TestOutcomesAndRefusals(unittest.TestCase):
    def test_non_resolved_yields_observation_record_without_fact(self):
        for outcome in ("AMBIGUOUS", "UNRESOLVED"):
            r = run([ok(outcome=outcome)])
            self.assertEqual(r.committed_fragments, ())
            entry = [e for e in r.journal_entries if e["fragment_id"] == "f1"][0]
            self.assertEqual(entry["kind"], "observation_record")
            self.assertEqual(entry["outcome"], outcome)

    def test_known_mapping_missing_refuses_durable(self):
        r = run([ok(known_mapping_missing=True)])
        self.assertEqual(r.committed_fragments, ())  # T6 not called for it
        entry = [e for e in r.journal_entries if e["fragment_id"] == "f1"][0]
        self.assertEqual(entry["kind"], "resolution_log")
        self.assertEqual(entry["code"], "CANONICAL_MAPPING_MISSING")

    def test_candidate_source_exhausted_durable_audit(self):
        r = run([ok(outcome="NO_CANDIDATE", candidate_source_exhausted=True)])
        entry = [e for e in r.journal_entries if e["fragment_id"] == "f1"][0]
        self.assertEqual(entry["kind"], "observation_record")
        self.assertEqual(entry["code"], "CANDIDATE_SOURCE_EXHAUSTED")


class TestEligibilityAndIdempotency(unittest.TestCase):
    def test_foreign_owner_is_integrity_error(self):
        binding = InterpretationRunBinding()
        binding.acquire("OTHER", "obs1", 0)
        r = run([ok()], binding=binding)
        self.assertEqual(r.eligibility, "INTEGRITY_ERROR")
        self.assertEqual(r.committed_fragments, ())
        self.assertEqual(r.journal_entries, ())

    def test_same_owner_proceeds(self):
        binding = InterpretationRunBinding()
        binding.acquire("R1", "obs1", 0)
        r = run([ok()], binding=binding)
        self.assertEqual(r.eligibility, "OK")
        self.assertEqual(r.committed_fragments, ("f1",))

    def test_investigation_only_emits_audit_not_fact(self):
        r = run([ok()], investigation_only=True)
        self.assertEqual(r.eligibility, "INVESTIGATION_ONLY")
        self.assertEqual(r.committed_fragments, ())  # never a canonical fact
        self.assertTrue(any(e["kind"] == "candidate_audit" for e in r.journal_entries))

    def test_marker_early_refusal_not_journaled(self):
        r = run([ok()], marker_exists=True)
        self.assertEqual(r.eligibility, "MARKER_REFUSED")
        self.assertEqual(r.committed_fragments, ())
        self.assertEqual(r.journal_entries, ())  # refused immediately, not written to the journal

    def test_same_batch_hash_is_idempotent(self):
        first = run([ok()])
        again = run([ok()], existing_batch_hashes=frozenset({first.batch_hash}))
        self.assertTrue(again.idempotent)
        self.assertEqual(again.journal_entries, ())  # no duplicate journal entry


if __name__ == "__main__":
    unittest.main()
