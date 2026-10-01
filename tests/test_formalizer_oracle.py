# -*- coding: utf-8 -*-
"""WP1.6 / WC1 — machine-readable oracle harness tests (V7 §11.2).

Proves each of the five comparison rules in isolation, then ``run_case`` end-to-end with a stub runner
(both passing and failing), and finally that real CoverageStatus output from assemble_candidate_ir flows
through the harness. The full A/DR matrix is filled at G3/G4; this gates the P1-applicable subset.
"""

import unittest

from ah.formalizer.candidate_ir import assemble_candidate_ir
from ah.formalizer.oracle import (
    Expected, OracleCase, RawInput, check_forbidden_conclusions, compare_diagnostics_multiset,
    compare_id_sets, compare_state_delta, canonical_hash, replay_identical, run_case,
)
from ah.formalizer.state import FormalizationState, TokenEvidence


class TestComparisonRules(unittest.TestCase):
    def test_rule1_id_set_exact(self):
        self.assertEqual(compare_id_sets(("a", "b"), ["b", "a"]), [])  # order-insensitive
        self.assertTrue(any("missing" in d for d in compare_id_sets(("a", "b"), ("a",))))

    def test_rule2_diagnostics_multiset(self):
        self.assertEqual(compare_diagnostics_multiset((("X", "l1"),), [("X", "l1")]), [])
        # a duplicate is significant: multiset, not set
        self.assertTrue(compare_diagnostics_multiset((("X", "l1"),), [("X", "l1"), ("X", "l1")]))

    def test_rule3_forbidden_absence(self):
        self.assertEqual(check_forbidden_conclusions(("INVENTED_ID",), ["clean text"]), [])
        self.assertEqual(check_forbidden_conclusions(("INVENTED_ID",), ["has INVENTED_ID here"]), ["INVENTED_ID"])

    def test_rule4_state_delta_by_hash_not_text(self):
        obj = {"k": 1}
        h = canonical_hash(obj)
        self.assertEqual(compare_state_delta((h,), [obj]), [])          # same structure -> same hash
        self.assertTrue(compare_state_delta((h,), [{"k": 2}]))         # different structure -> diff

    def test_rule5_replay_identity(self):
        self.assertTrue(replay_identical({"a": 1}, {"a": 1}))
        self.assertFalse(replay_identical({"a": 1}, {"a": 2}))


class TestRunCase(unittest.TestCase):
    def _case(self, **exp_kw):
        return OracleCase(case_id="A02", raw_input=RawInput(text="x"), expected=Expected(**exp_kw))

    def test_passing_case(self):
        case = self._case(candidate_ids=("V1",), coverage_status="FULL_CANONICAL")
        runner = lambda ri: {"candidate_ids": ["V1"], "coverage_status": "FULL_CANONICAL"}
        rep = run_case(case, runner)
        self.assertTrue(rep.passed, rep.failures)

    def test_failing_case_reports_each_rule(self):
        case = self._case(candidate_ids=("V1",), coverage_status="FULL_CANONICAL",
                          forbidden_conclusions=("BAD",))
        runner = lambda ri: {"candidate_ids": ["V2"], "coverage_status": "PARTIAL",
                            "final_texts": ["contains BAD"]}
        rep = run_case(case, runner)
        self.assertFalse(rep.passed)
        self.assertTrue(any("candidates" in f for f in rep.failures))
        self.assertTrue(any("coverage" in f for f in rep.failures))
        self.assertTrue(any("forbidden" in f for f in rep.failures))

    def test_absent_expected_fields_not_checked(self):
        case = OracleCase(case_id="A02", raw_input=RawInput(text="x"))  # empty Expected
        rep = run_case(case, lambda ri: {"candidate_ids": ["whatever"]})
        self.assertTrue(rep.passed)


class TestRealCoverageThroughHarness(unittest.TestCase):
    def test_full_canonical_flows_through_run_case(self):
        st = FormalizationState.new("У меня есть книга.")
        st.evidence.extend(TokenEvidence(span=s) for s in ("у", "меня", "есть", "книга"))

        case = OracleCase(
            case_id="A08", raw_input=RawInput(text="У меня есть книгу."),
            expected=Expected(coverage_status="FULL_CANONICAL"),
        )
        runner = lambda ri: {
            "coverage_status": assemble_candidate_ir(st).coverage.level,
        }
        rep = run_case(case, runner)
        self.assertTrue(rep.passed, rep.failures)


if __name__ == "__main__":
    unittest.main()
