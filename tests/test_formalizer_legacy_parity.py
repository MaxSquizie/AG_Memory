# -*- coding: utf-8 -*-
"""Path B slice A — behavioral parity harness vs the legacy adaptive_parser (V7 §12 / WP3.5).

The legacy parser is a BEHAVIORAL REFERENCE only, never an unconditionally correct standard, so this test
deliberately does NOT assert agreement between the two sides. It pins the property that actually matters for a
replacement candidate — the new pipeline is DETERMINISTIC (re-run -> identical projection) on the demo set — and
provides the comparison surface (new decision outcomes vs legacy completion status) with divergence recorded, not failed.

The real legacy parser is constructed lazily; if its dependencies are unavailable in an environment it degrades to
no-legacy-recording rather than failing import. With a permissive empty LLM backend the legacy side reports ERROR for
every sentence (it needs a live model); that is a legitimate recorded outcome, not a test failure. A real-model parity
run feeds both sides the same local backend and reuses this exact harness.
"""

import unittest

from ah.formalizer.legacy_compare import (
    DEMO_SENTENCES,
    LegacyAdapter,
    build_real_legacy_parse_fn,
    compare,
    new_pipeline_projection,
)

_VALID_LEGACY_STATUS = {"COMPLETED", "CLARIFICATION_REQUIRED", "ERROR"}


class LegacyParityTest(unittest.TestCase):
    def setUp(self):
        parse_fn = build_real_legacy_parse_fn()  # None if the legacy parser cannot be constructed here
        self.adapter = LegacyAdapter(parse_fn) if parse_fn else None

    def test_new_pipeline_is_deterministic_on_demo_set(self):
        for label in sorted(DEMO_SENTENCES):
            text = DEMO_SENTENCES[label]
            first = new_pipeline_projection(text)
            second = new_pipeline_projection(text)
            self.assertEqual(first, second, f"{label}: pipeline is not deterministic")
            # Every demo sentence yields exactly one predicate_value decision (the Phase 1 vertical).
            slots = [slot for slot, _ in first["decisions"]]
            self.assertIn("predicate_value", slots)

    def test_comparison_harness_records_both_sides_without_asserting_agreement(self):
        if self.adapter is None:
            self.skipTest("legacy parser unavailable in this environment")
        rows = compare(DEMO_SENTENCES, new_pipeline_projection, self.adapter)
        self.assertEqual(len(rows), len(DEMO_SENTENCES))
        for row in rows:
            # New side always projects a decision; legacy status is recorded from the allowed set (no agreement asserted).
            self.assertTrue(row.new_decisions, f"{row.label}: no new-side decisions projected")
            self.assertIn(row.legacy_status, _VALID_LEGACY_STATUS)


if __name__ == "__main__":
    unittest.main()
