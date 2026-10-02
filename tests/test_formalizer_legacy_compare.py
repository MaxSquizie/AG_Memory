# -*- coding: utf-8 -*-
"""WP3.5 — Behavioral comparison harness tests (V7 §12). Legacy = behavioral reference only, never ground truth."""

import unittest

from ah.formalizer import legacy_compare as lc


class _ClarificationRequired(Exception):
    pass


def _stub_new(text, mode="baseline"):
    return {"decisions": [("pred", "RESOLVED" if text.endswith("лапки.") else "UNRESOLVED")],
            "diagnostics": []}


def _make_legacy(behavior: dict):
    def parse_fn(text):
        b = behavior.get(text)
        if b == "raise_clarify":
            raise _ClarificationRequired("need clarification")
        if b == "raise_err":
            raise ValueError("boom")
        return None  # completed
    return lc.LegacyAdapter(parse_fn)


class TestComparisonHarness(unittest.TestCase):
    def test_one_row_per_sentence_with_well_formed_statuses(self):
        sentences = {"S1": "a.", "S2": "b."}
        legacy = _make_legacy({"a.": None, "b.": "raise_clarify"})
        rows = lc.compare(sentences, _stub_new, legacy)
        self.assertEqual([r.label for r in rows], ["S1", "S2"])
        self.assertEqual(rows[0].legacy_status, "COMPLETED")
        self.assertEqual(rows[1].legacy_status, "CLARIFICATION_REQUIRED")

    def test_comparison_is_deterministic(self):
        sentences = dict(lc.DEMO_SENTENCES)
        legacy = _make_legacy({t: None for t in sentences.values()})
        r1 = lc.compare(sentences, _stub_new, legacy)
        r2 = lc.compare(sentences, _stub_new, legacy)
        self.assertEqual([(r.label, r.new_decisions, r.legacy_status) for r in r1],
                         [(r.label, r.new_decisions, r.legacy_status) for r in r2])

    def test_legacy_adapter_maps_exception_kinds(self):
        self.assertEqual(lc.LegacyAdapter(lambda t: None).status("x"), "COMPLETED")
        self.assertEqual(_make_legacy({"x": "raise_clarify"}).status("x"), "CLARIFICATION_REQUIRED")
        self.assertEqual(_make_legacy({"x": "raise_err"}).status("x"), "ERROR")

    def test_divergence_is_recorded_not_asserted(self):
        # new side resolves S1; legacy reports ERROR for it -> divergence is a recorded fact, not a failure
        resolved_new = lambda text, mode="baseline": {"decisions": [("pred", "RESOLVED")], "diagnostics": []}
        rows = lc.compare({"S1": "a."}, resolved_new, _make_legacy({"a.": "raise_err"}))
        self.assertTrue(rows[0].new_has_resolved)
        self.assertEqual(rows[0].legacy_status, "ERROR")   # recorded; the harness does not fail on it

    def test_real_new_pipeline_is_deterministic(self):
        try:
            first = {lab: lc.new_pipeline_projection(text) for lab, text in lc.DEMO_SENTENCES.items()}
        except Exception as exc:  # pragma: no cover - environment dependent (schema/morphology availability)
            self.skipTest(f"real pipeline unavailable: {exc}")
        second = {lab: lc.new_pipeline_projection(text) for lab, text in lc.DEMO_SENTENCES.items()}
        self.assertEqual(first, second)   # identical input -> identical projection through the whole T0-T4


if __name__ == "__main__":
    unittest.main()
