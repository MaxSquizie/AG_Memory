# -*- coding: utf-8 -*-
"""IF/hypothetical -> production GoalMode seam (V7 §6.2/§6.3).

Proves the experimental text-level IF surface feeds the *existing* typed, non-lexical counterfactual path unchanged:
paired clause detection becomes a HYPOTHETICAL assumption + QUERY target + SUBORDINATE dependency that
``apply_speech_act_scoping`` consumes (shadow ``__CF_TARGET__``). Unpaired / single-clause input is honest UNBOUND —
surface words alone never open a counterfactual scope.
"""

from __future__ import annotations

import unittest

from ah.formalizer.tag_source import TagSource
from ah.inference.if_bridge import if_to_perception
from ah.perception import AssertionStatus, QueryMode, apply_speech_act_scoping


class TestIfBridge(unittest.TestCase):
    def setUp(self) -> None:
        self.ts = TagSource()

    def test_if_pair_produces_typed_perception(self) -> None:
        p = if_to_perception("Если сервер работает, сервис отвечает.", self.ts)
        self.assertIsNotNone(p)
        # Antecedent is a HYPOTHETICAL assertion (typed status, not lexical).
        self.assertEqual(len(p.assertions), 1)
        self.assertIs(p.assertions[0].status, AssertionStatus.HYPOTHETICAL)
        # Consequent is an EXISTS query target.
        self.assertEqual(len(p.queries), 1)
        self.assertIs(p.queries[0].query_mode, QueryMode.EXISTS)
        # Linked by a SUBORDINATE act dependency (the counterfactual scope edge).
        self.assertEqual(
            [(d.parent_ref, d.child_ref, d.kind.name) for d in p.act_dependencies],
            [("Q1", "A1", "SUBORDINATE")],
        )

    def test_structural_content_is_morph_derived(self) -> None:
        p = if_to_perception("Если сервер работает, сервис отвечает.", self.ts)
        # Subject mention is the first NOUN of the antecedent; predicate its first VERB (morph category -> syntax).
        self.assertEqual(p.assertions[0].actants[0].mention, "сервер")
        self.assertEqual(p.assertions[0].predicate.surface, "работает")

    def test_flows_through_speech_act_scoping(self) -> None:
        # The KEY vertical proof: IF detection feeds the production scoping boundary unchanged.
        p = if_to_perception("Если сервер работает, сервис отвечает.", self.ts)
        scoped = apply_speech_act_scoping(p)
        shadows = [a.local_id for a in scoped.assertions if a.local_id.endswith("__CF_TARGET__")]
        self.assertEqual(shadows, ["Q1:__CF_TARGET__"])

    def test_single_clause_is_not_counterfactual(self) -> None:
        # No paired IF boundaries -> honest UNBOUND (None), never guessed.
        self.assertIsNone(if_to_perception("Вороны любят червей.", self.ts))

    def test_unpaired_subordinator_not_invented_from_surface_words(self) -> None:
        # "когда" is an ambiguous subordinator; without a confirming probe it stays content, so no IF pair opens.
        self.assertIsNone(if_to_perception("Когда идёт дождь, земля мокрая.", self.ts))

    def test_scoping_is_idempotent_under_reapplication(self) -> None:
        p = if_to_perception("Если сервер работает, сервис отвечает.", self.ts)
        once = apply_speech_act_scoping(p)
        twice = apply_speech_act_scoping(once)
        shadows = [a.local_id for a in twice.assertions if a.local_id.endswith("__CF_TARGET__")]
        self.assertEqual(shadows, ["Q1:__CF_TARGET__"])


if __name__ == "__main__":
    unittest.main()
