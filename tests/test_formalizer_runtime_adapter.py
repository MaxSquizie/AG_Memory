# -*- coding: utf-8 -*-
"""Path B slice 1 — FormalizerAdapter emits the product PerceptionResult (V7 §14 / integration).

Proves the replacement seam is real and HONEST without a live model (FakeSelector drives it):
a resolved unique pick becomes an assertion with STRUCTURALLY-assigned roles and a REAL predicate
(surface + lemma carried from evidence); ambiguous/unresolved decisions are NOT collapsed to a
fabricated single value — they surface as explicit notes. The relation id (V1/V2/...) is internal to the
formalizer; the product model keys on real words, so it is not exposed in PerceptionResult.
"""

import unittest

from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.runtime_adapter import FormalizerAdapter


class RuntimeAdapterSlice1Test(unittest.TestCase):
    def test_s3_baseline_have_becomes_assertion(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("У меня есть книга.")  # ONE_SELECTED V1 -> RESOLVED (copula "есть")
        self.assertEqual(len(res.assertions), 1)
        a = res.assertions[0]
        self.assertEqual(a.predicate.surface, "есть")  # real copula carried from evidence, not a label
        self.assertEqual(a.predicate.normalized_hint, "быть")
        from ah.model.types import ActantRole as R

        roles = [act.role for act in a.actants]
        self.assertIn(R.SUBJECT, roles)
        self.assertIn(R.OBJECT, roles)

    def test_s6_baseline_like_verbal_frame(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("Вороны любят червей.")  # ONE_SELECTED V4 -> RESOLVED (verbal NOM+V+ACC)
        self.assertEqual(len(res.assertions), 1)
        self.assertEqual(res.assertions[0].predicate.normalized_hint, "любить")  # real verb lemma
        from ah.model.types import ActantRole as R

        roles = [act.role for act in res.assertions[0].actants]
        self.assertIn(R.SUBJECT, roles)
        self.assertIn(R.OBJECT, roles)

    def test_s1_baseline_ambiguous_not_fabricated(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("У вороны есть лапки.")  # MULTIPLE_ADMISSIBLE -> UNRESOLVED (no per-value ground)
        self.assertEqual(len(res.assertions), 0, "an unresolved decision must not fabricate a single assertion")
        self.assertTrue(any(d.startswith("UNRESOLVED_PREDICATE") for d in res.diagnostics))

    def test_s1_augmented_resolves_via_context(self):
        adapter = FormalizerAdapter(FakeSelector.demo("augmented"))
        # Without the declared contextual statement S1 stays unresolved (see baseline test above); with it,
        # the HAS_PART reading is grounded and a single assertion is emitted.
        res = adapter.parse(
            "У вороны есть лапки.",
            context_facts=("Лапки — часть тела этой вороны.",),
        )
        self.assertEqual(len(res.assertions), 1)
        self.assertEqual(res.assertions[0].predicate.surface, "есть")


if __name__ == "__main__":
    unittest.main()
