# -*- coding: utf-8 -*-
"""Acceptance tests for the coverage / miss accumulator (V7 §2.3)."""

import unittest

from ah.formalizer.coverage import summarize


class _Dec:
    def __init__(self, slot_id="predicate_value", outcome=None):
        self.slot_id = slot_id
        self.outcome = outcome


class _Diag:
    def __init__(self, code):
        self.code = code
        self.detail = ""


class _State:
    def __init__(self, decisions=(), diagnostics=()):
        self.decisions = {f"k{i}": d for i, d in enumerate(decisions)}
        self.diagnostics = list(diagnostics)


class TestCoverage(unittest.TestCase):
    def test_answered_sentence_and_ratio(self):
        rep = summarize([_State([_Dec(outcome="RESOLVED")]), _State([_Dec(outcome="UNRESOLVED")])])
        self.assertEqual(rep.sentences, 2)
        self.assertEqual(rep.answered_sentences, 1)
        self.assertEqual(rep.proven_outcomes, 1)
        self.assertAlmostEqual(rep.coverage_ratio, 0.5)

    def test_ambiguous_counts_as_proven(self):
        rep = summarize([_State([_Dec(outcome="AMBIGUOUS")])])
        self.assertEqual(rep.answered_sentences, 1)
        self.assertEqual(rep.proven_outcomes, 1)

    def test_honest_gap_tracked_separately_from_provider_failure(self):
        st = _State(
            [_Dec(outcome="UNRESOLVED")],
            diagnostics=[_Diag("NO_CANDIDATE"), _Diag("PROVIDER_UNAVAILABLE")],
        )
        rep = summarize([st])
        self.assertEqual(rep.honest_gaps.get("NO_CANDIDATE"), 1)
        self.assertEqual(rep.provider_failures.get("PROVIDER_UNAVAILABLE"), 1)
        # A provider outage is infrastructure, NOT a semantic coverage gap.
        self.assertNotIn("PROVIDER_UNAVAILABLE", rep.honest_gaps)
        self.assertEqual(rep.answered_sentences, 0)

    def test_protocol_error_is_provider_not_honest(self):
        rep = summarize([_State(diagnostics=[_Diag("PROTOCOL_ERROR")])])
        self.assertEqual(rep.provider_failures.get("PROTOCOL_ERROR"), 1)
        self.assertEqual(rep.honest_gap_total, 0)

    def test_empty_batch_ratio_zero(self):
        rep = summarize([])
        self.assertEqual(rep.coverage_ratio, 0.0)
        self.assertEqual(rep.decisions, 0)

    def test_multiple_gaps_accumulate(self):
        states = [
            _State([_Dec(outcome="UNRESOLVED")], [_Diag("NO_CANDIDATE"), _Diag("REFERENCE_UNKNOWN")]),
            _State([_Dec(outcome="UNRESOLVED")], [_Diag("STRUCTURE_NOT_COVERED")]),
        ]
        rep = summarize(states)
        self.assertEqual(rep.honest_gaps.get("NO_CANDIDATE"), 1)
        self.assertEqual(rep.honest_gaps.get("REFERENCE_UNKNOWN"), 1)
        self.assertEqual(rep.honest_gaps.get("STRUCTURE_NOT_COVERED"), 1)
        self.assertEqual(rep.honest_gap_total, 3)


if __name__ == "__main__":
    unittest.main()
