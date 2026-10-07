# -*- coding: utf-8 -*-
"""I02 — write-boundary gate: a question is never asserted as a world fact, an imperative is a
directive (not a fact), and a negated declarative is NOT(P) (never a positive fact).

These tests drive ``FormalizerAdapter._to_perception_result`` directly with hand-built states so the
gate logic is proven deterministically (no LLM, no pymorphy3 flakiness): the speech act + NEG scope are
decided ONCE for the utterance and constrain every emitted candidate regardless of what the selector said.
"""

import unittest

from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.speech_act import detect_negation
from ah.formalizer.state import (
    Decision,
    FrameCandidate,
    FormalizationState,
    MorphVariant,
    TokenEvidence,
)


def _state(text: str, verb_span: str, verb_lemma: str, participants=(), mood=None):
    """One verbal frame with a single RESOLVED unique predicate pick (the write-boundary input)."""
    st = FormalizationState.new(text)
    st.evidence = [TokenEvidence(span=verb_span, lemma=verb_lemma, pos="VERB",
                                variants=(MorphVariant(lemma=verb_lemma, pos="VERB", mood=mood),))]
    for p in participants:
        st.evidence.append(TokenEvidence(span=p, lemma=p, pos="NOUN",
                                        variants=(MorphVariant(lemma=p, pos="NOUN"),)))
    frame = FrameCandidate(frame_id="F1", kind="FLAT", anchor_span=verb_span, participants=tuple(participants))
    st.frames.append(frame)
    dec = Decision(slot_id="predicate_value", frame_id="F1", candidates=("V4",), selected=("V4",), outcome="RESOLVED")
    st.decisions["F1|predicate_value"] = dec
    return st


class DetectNegationTest(unittest.TestCase):
    def test_plain_negation(self):
        self.assertTrue(detect_negation("Вороны не любят червей."))

    def test_no_negation(self):
        self.assertFalse(detect_negation("Вороны любят червей."))

    def test_ni_marker(self):
        self.assertTrue(detect_negation("Никто не пришёл."))


class WriteBoundaryGateTest(unittest.TestCase):
    def setUp(self):
        # _to_perception_result never touches the selector; a sentinel keeps the test isolated from it.
        self.adapter = FormalizerAdapter(selector=object())

    def test_declarative_asserts_positive_fact(self):
        res = self.adapter._to_perception_result(_state("Вороны любят червей.", "любят", "любить", ("Вороны", "червей")))
        self.assertEqual(len(res.assertions), 1)
        self.assertFalse(res.assertions[0].negated)
        self.assertEqual(len(res.queries), 0)
        self.assertEqual(len(res.commands), 0)

    def test_negated_declarative_is_not_positive_fact(self):
        # I02 core: "не любят" must be represented as NOT(P), never a positive assertion.
        res = self.adapter._to_perception_result(_state("Вороны не любят червей.", "любят", "любить", ("Вороны", "червей")))
        self.assertEqual(len(res.assertions), 1)
        self.assertTrue(res.assertions[0].negated, "a negated declarative must carry negated=True")
        self.assertEqual(len(res.queries), 0)
        self.assertTrue(any(d.startswith("NEGATED_ASSERTION") for d in res.diagnostics), res.diagnostics)

    def test_question_is_not_asserted(self):
        # DR27: a yes/no question's content is an EXISTS goal, never an asserted world fact.
        res = self.adapter._to_perception_result(_state("Вороны любят червей?", "любят", "любить", ("Вороны", "червей")))
        self.assertEqual(len(res.assertions), 0, "a question must not assert its content as a fact")
        self.assertEqual(len(res.queries), 1)
        from ah.perception.contracts import QueryMode

        self.assertIs(res.queries[0].query_mode, QueryMode.EXISTS)
        self.assertTrue(any(d.startswith("SPEECH_ACT_QUERY") for d in res.diagnostics), res.diagnostics)

    def test_imperative_is_a_directive_not_a_fact(self):
        # An imperative verb (mood=imperative) is a directive: routed to commands, never asserted.
        res = self.adapter._to_perception_result(_state("Открой окно.", "открой", "открыть", ("окно",), mood="imperative"))
        self.assertEqual(len(res.assertions), 0, "an imperative must not be asserted as a world fact")
        self.assertEqual(len(res.commands), 1)
        self.assertTrue(any(d.startswith("SPEECH_ACT_COMMAND") for d in res.diagnostics), res.diagnostics)


if __name__ == "__main__":
    unittest.main()
