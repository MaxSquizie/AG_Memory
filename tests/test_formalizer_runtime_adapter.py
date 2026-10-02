# -*- coding: utf-8 -*-
"""Path B slice 1 — NewFormalizerAdapter emits the product PerceptionResult (V7 §14 / integration).

Proves the replacement seam is real and HONEST without a live model (FakeSelector drives it):
resolved unique picks become assertions with structurally-assigned roles; ambiguous/unresolved
decisions are NOT collapsed to a fabricated single value — they surface as explicit notes.
"""

import unittest

from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.runtime_adapter import NewFormalizerAdapter


def _hints(result):
    return [a.predicate.normalized_hint for a in result.assertions]


class RuntimeAdapterSlice1Test(unittest.TestCase):
    def test_s3_baseline_have_becomes_assertion(self):
        adapter = NewFormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("У меня есть книга.")  # ONE_SELECTED V1 -> RESOLVED
        self.assertEqual(len(res.assertions), 1)
        a = res.assertions[0]
        self.assertEqual(a.predicate.normalized_hint, "V1")  # HAVE
        roles = [act.role for act in a.actants]
        from ah.model.types import ActantRole as R

        self.assertIn(R.SUBJECT, roles)
        self.assertIn(R.OBJECT, roles)

    def test_s6_baseline_like_verbal_frame(self):
        adapter = NewFormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("Вороны любят червей.")  # ONE_SELECTED V4 -> RESOLVED (verbal NOM+V+ACC)
        self.assertEqual(_hints(res), ["V4"])  # LIKE
        from ah.model.types import ActantRole as R

        roles = [act.role for act in res.assertions[0].actants]
        self.assertIn(R.SUBJECT, roles)
        self.assertIn(R.OBJECT, roles)

    def test_s1_baseline_ambiguous_not_fabricated(self):
        adapter = NewFormalizerAdapter(FakeSelector.demo("baseline"))
        res = adapter.parse("У вороны есть лапки.")  # MULTIPLE_ADMISSIBLE -> UNRESOLVED (no per-value ground)
        self.assertEqual(len(res.assertions), 0, "an unresolved decision must not fabricate a single assertion")
        self.assertTrue(any(d.startswith("UNRESOLVED_PREDICATE") for d in res.diagnostics))

    def test_s1_augmented_resolves_has_part(self):
        adapter = NewFormalizerAdapter(FakeSelector.demo("augmented"))
        res = adapter.parse(
            "У вороны есть лапки.",
            context_facts=("Лапки — часть тела этой вороны.",),  # declared -> C ground + M(V2) -> RESOLVED
        )
        self.assertEqual(_hints(res), ["V2"])  # HAS_PART


if __name__ == "__main__":
    unittest.main()
