# -*- coding: utf-8 -*-
"""D — Open-set value-generation *trigger* (V7 §2.3/§5.x).

Proves the deferred open-set mechanism is gated on accumulated honest misses: it proposes an extension only when
NO_CANDIDATE recurs across enough DISTINCT inputs, and otherwise stays silent (never invents values, never auto-applies).
"""

import unittest


def _miss_state(text):
    from ah.formalizer.state import Decision, FormalizationState

    st = FormalizationState.new(text)
    st.decisions["C2|predicate_value"] = Decision(
        slot_id="predicate_value", frame_id="C2", candidates=("V1", "V2"), outcome="NO_CANDIDATE"
    )
    return st


def _resolved_state(text):
    from ah.formalizer.state import Decision, FormalizationState

    st = FormalizationState.new(text)
    st.decisions["C2|predicate_value"] = Decision(
        slot_id="predicate_value", frame_id="C2", candidates=("V1", "V2"), selected=("V1",), outcome="RESOLVED"
    )
    return st


class TestOpenSetGate(unittest.TestCase):
    def test_below_threshold_no_proposal(self):
        from ah.formalizer.open_set_gate import evaluate_open_set

        states = [_miss_state("У кота есть усы."), _miss_state("У дома есть крыша.")]  # only 2 distinct
        self.assertIsNone(evaluate_open_set(states, min_distinct=3))

    def test_at_threshold_proposes(self):
        from ah.formalizer.open_set_gate import evaluate_open_set

        states = [
            _miss_state("У кота есть усы."),
            _miss_state("У дома есть крыша."),
            _miss_state("У дерева есть ветви."),
        ]
        prop = evaluate_open_set(states, min_distinct=3)
        self.assertIsNotNone(prop)
        self.assertEqual(prop.distinct_miss_inputs, 3)
        self.assertEqual(prop.total_misses, 3)

    def test_resolved_sentences_are_not_counted(self):
        from ah.formalizer.open_set_gate import evaluate_open_set

        states = [
            _miss_state("У кота есть усы."),
            _resolved_state("Вороны любят червей."),  # resolved -> not a miss
            _resolved_state("У стола есть ножки."),   # resolved -> not a miss
        ]
        self.assertIsNone(evaluate_open_set(states, min_distinct=3))

    def test_repeated_same_sentence_does_not_inflate(self):
        from ah.formalizer.open_set_gate import evaluate_open_set

        states = [_miss_state("У кота есть усы.")] * 5  # same input repeated -> 1 distinct
        self.assertIsNone(evaluate_open_set(states, min_distinct=3))


if __name__ == "__main__":
    unittest.main()
