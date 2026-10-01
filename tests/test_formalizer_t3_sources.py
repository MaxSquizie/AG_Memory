# -*- coding: utf-8 -*-
"""5-source candidate contract tests (V7 §5.1 / WP1.2).

Proves the exhaustive trace rules in isolation, then that a real run records five ordered traces per
decision without blocking the search (so existing Phase 1 outcomes are unchanged).
"""

import unittest

from ah.formalizer.t3_sources import (
    BLOCKED, CHECKED_EMPTY, FOUND, NOT_APPLICABLE, CandidateSourceTrace, build_source_traces,
    found_count, no_candidate_allowed, resolved_allowed, search_blocked,
)


class TestTraceConstruction(unittest.TestCase):
    def test_five_ordered_traces_with_default_phase1_inputs(self):
        tr = build_source_traces("F1", "predicate_value", schema_candidates=("HAVE", "HAS_PART"))
        self.assertEqual([t.source_id for t in tr], [1, 2, 3, 4, 5])
        by = {t.source_id: t.status for t in tr}
        self.assertEqual(by[1], FOUND)                 # schema value_ids present
        self.assertEqual(tr[0].candidate_ids, ("HAVE", "HAS_PART"))
        self.assertEqual(by[2], CHECKED_EMPTY)         # R-S read, none (default applicable)
        self.assertEqual(by[3], NOT_APPLICABLE)       # no R-X3 store wired (Phase 1 default)
        self.assertEqual(by[4], CHECKED_EMPTY)        # declared reads -> C-grounds only
        self.assertEqual(by[5], CHECKED_EMPTY)        # deterministic open path checked, none

    def test_not_applicable_requires_reason(self):
        with self.assertRaises(ValueError):
            CandidateSourceTrace("F1", "s", 2, NOT_APPLICABLE)

    def test_found_requires_candidates(self):
        with self.assertRaises(ValueError):
            CandidateSourceTrace("F1", "s", 1, FOUND)

    def test_bad_status_rejected(self):
        with self.assertRaises(ValueError):
            CandidateSourceTrace("F1", "s", 1, "MAYBE")

    def test_source5_unverified_path_is_blocked(self):
        tr = build_source_traces("F1", "predicate_value", schema_candidates=("HAVE",),
                                 open_path_verified=False)
        self.assertEqual(tr[4].status, BLOCKED)
        self.assertTrue(search_blocked(tr))


class TestDecisionRules(unittest.TestCase):
    def test_found_candidate_under_blocked_search_is_not_unique(self):
        # §5.1 core invariant: a candidate found by one source is NOT unique while an applicable
        # source is BLOCKED -> forbids BOTH NO_CANDIDATE and RESOLVED.
        tr = build_source_traces("F1", "predicate_value", schema_candidates=("HAVE",),
                                 blocked=frozenset({3}), blocked_reasons={3: "R-X3 provider down"})
        self.assertEqual(found_count(tr), 1)
        self.assertTrue(search_blocked(tr))
        self.assertFalse(no_candidate_allowed(tr))
        self.assertFalse(resolved_allowed(tr, has_positive_grounds=True))

    def test_no_candidate_only_after_five_terminal_empty(self):
        tr = build_source_traces("F1", "predicate_value")  # no schema candidates -> all terminal empty
        self.assertEqual(found_count(tr), 0)
        self.assertTrue(no_candidate_allowed(tr))

    def test_blocked_forbids_no_candidate_even_when_empty(self):
        tr = build_source_traces("F1", "predicate_value", blocked=frozenset({5}),
                                 blocked_reasons={5: "budget exhausted"})
        self.assertFalse(no_candidate_allowed(tr))


class TestIntegration(unittest.TestCase):
    def test_run_records_five_unblocked_traces_per_decision(self):
        from ah.formalizer.pipeline import run
        from ah.formalizer.fake_selector import FakeSelector
        from ah.formalizer.selection_protocol import load_decision_schema

        st = run("У вороны есть лапки.", load_decision_schema(), FakeSelector.demo("baseline"))
        self.assertTrue(st.decisions, "expected at least one decision")
        for dec in st.decisions.values():
            self.assertEqual(len(dec.source_traces), 5)
            self.assertEqual([t.source_id for t in dec.source_traces], [1, 2, 3, 4, 5])
            self.assertFalse(search_blocked(dec.source_traces))  # Phase 1 search is complete


if __name__ == "__main__":
    unittest.main()
