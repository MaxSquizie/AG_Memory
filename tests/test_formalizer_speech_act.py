# -*- coding: utf-8 -*-
"""B — Speech-act / indirect request (V7 §18 DR27, A37).

Proves the new formalizer handles an indirect request «Ты не мог бы открыть окно?»: linked QUERY/COMMAND
alternatives when context does not determine the act, a grounded single reading when it does, and — crucially —
that NO world fact about the requested action is ever asserted (the AH delta stays empty for question content).
"""

import unittest


class TestDetectSpeechAct(unittest.TestCase):
    def test_indirect_request_yields_linked_alternatives(self):
        from ah.formalizer.speech_act import detect_speech_act, has_linked_alternatives

        readings = detect_speech_act("Ты не мог бы открыть окно?")
        kinds = {r.kind for r in readings}
        self.assertEqual(kinds, {"QUERY", "COMMAND"})
        self.assertTrue(all(not r.grounded for r in readings))  # form-inferred, not context-grounded
        self.assertTrue(has_linked_alternatives(readings))

    def test_explicit_request_kind_grounds_single_reading(self):
        from ah.formalizer.speech_act import detect_speech_act

        readings = detect_speech_act("Ты не мог бы открыть окно?", ("request_kind=COMMAND",))
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].kind, "COMMAND")
        self.assertTrue(readings[0].grounded)

    def test_plain_question_is_query(self):
        from ah.formalizer.speech_act import detect_speech_act

        readings = detect_speech_act("Где книга?")
        self.assertEqual([(r.kind, r.grounded) for r in readings], [("QUERY", True)])

    def test_declarative(self):
        from ah.formalizer.speech_act import detect_speech_act

        readings = detect_speech_act("Вороны любят червей.")
        self.assertEqual([(r.kind, r.grounded) for r in readings], [("DECLARATIVE", True)])


class TestAdapterSurfacesReadingWithoutAssertingAction(unittest.TestCase):
    def test_indirect_request_is_not_asserted(self):
        from ah.formalizer.fake_selector import FakeSelector
        from ah.formalizer.runtime_adapter import FormalizerAdapter

        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        result = adapter.parse("Ты не мог бы открыть окно?")

        # The reading is surfaced as a diagnostic...
        self.assertTrue(any(d.startswith("SPEECH_ACT_LINKED") for d in result.diagnostics), result.diagnostics)
        # ...and the requested action is NEVER asserted as a world fact (no predicate over the content).
        for assertion in result.assertions:
            hint = (assertion.predicate.normalized_hint or "").lower()
            self.assertNotIn("откр", hint)
            self.assertNotIn("окон", hint)


if __name__ == "__main__":
    unittest.main()
