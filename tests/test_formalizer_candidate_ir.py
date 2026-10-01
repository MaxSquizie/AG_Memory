# -*- coding: utf-8 -*-
"""WP1.5 — CandidateIR assembly + CoverageStatus tests (V7 §1.3).

Coverage is orthogonal to Decision.outcome: it measures how much of the input is structurally covered,
not whether any decision resolved. The level rule and the immutable single-exit assembly are proven here.
"""

import unittest

from ah.formalizer.candidate_ir import (
    COVERAGE_LEVELS, CandidateIR, CoverageStatus, assemble_candidate_ir, compute_coverage,
)
from ah.formalizer.state import FormalizationState, TokenEvidence


class TestCoverageValidation(unittest.TestCase):
    def test_invalid_level_rejected(self):
        with self.assertRaises(ValueError):
            CoverageStatus(level="MAYBE")

    def test_covered_unresolved_overlap_rejected(self):
        with self.assertRaises(ValueError):
            CoverageStatus(level="PARTIAL", covered_span_ids=("s1",), unresolved_span_ids=("s1",))


class TestComputeCoverage(unittest.TestCase):
    def test_full_canonical_when_closed_and_covered(self):
        c = compute_coverage(("a", "b"))
        self.assertEqual(c.level, "FULL_CANONICAL")

    def test_open_lexical_when_isolated_open_t(self):
        c = compute_coverage(("a",), open_lexical=True)
        self.assertEqual(c.level, "OPEN_LEXICAL")

    def test_partial_when_some_unresolved(self):
        c = compute_coverage(("a",), ("b",))
        self.assertEqual(c.level, "PARTIAL")

    def test_none_when_only_unresolved(self):
        self.assertEqual(compute_coverage((), ("b",)).level, "NONE")

    def test_none_when_no_useful_candidate_and_nothing_covered(self):
        self.assertEqual(compute_coverage((), useful_candidate=False).level, "NONE")


class TestAssemble(unittest.TestCase):
    def _state_with(self, *tokens):
        st = FormalizationState.new("x")
        st.evidence.extend(TokenEvidence(span=t) for t in tokens)
        return st

    def test_all_resolved_is_full_canonical(self):
        ir = assemble_candidate_ir(self._state_with("s0", "s1"))
        self.assertIsInstance(ir, CandidateIR)
        self.assertEqual(ir.coverage.level, "FULL_CANONICAL")
        self.assertEqual(set(ir.coverage.covered_span_ids), {"s0", "s1"})

    def test_oov_token_is_partial(self):
        st = self._state_with("s0")
        st.evidence.append(TokenEvidence(span="oov_word", lex_status="OOV_KEEP_AS_IS"))
        ir = assemble_candidate_ir(st)
        self.assertEqual(ir.coverage.level, "PARTIAL")
        self.assertIn("oov_word", ir.coverage.unresolved_span_ids)

    def test_assembly_is_pure(self):
        st = self._state_with("s0")
        before = list(st.evidence)
        assemble_candidate_ir(st)
        self.assertEqual(list(st.evidence), before)  # read-only: no mutation


if __name__ == "__main__":
    unittest.main()
