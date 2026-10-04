# -*- coding: utf-8 -*-
"""A — Runtime path-B wiring (V7 §14).

Proves the production perception entry (``orchestrator_base -> services.perception.parse``) actually
delegates to the new formalizer vertical when a :class:`FormalizerAdapter` is attached, that legacy
stays the default when none is set, and that the bootstrap env-flag gate degrades gracefully.
"""

import os
import unittest


class _StubBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError("legacy backend must NOT be called when a formalizer is attached")


def _settings():
    from ah.perception.llm_parser import LLMPerceptionSettings

    return LLMPerceptionSettings()


class TestFormalizerDelegation(unittest.TestCase):
    def test_parse_delegates_to_formalizer_when_set(self):
        from ah.formalizer.fake_selector import FakeSelector
        from ah.formalizer.runtime_adapter import FormalizerAdapter
        from ah.perception.llm_parser import LLMPerceptionService

        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        svc = LLMPerceptionService(_StubBackend(), _settings(), formalizer=adapter)
        # S6 "Вороны любят червей." -> RESOLVED V4 (LIKE): the one baseline sentence that emits an assertion.
        result = svc.parse("Вороны любят червей.", None)  # interaction_context unused on this path

        self.assertEqual(result.source_text, "Вороны любят червей.")
        from ah.model.types import ActantRole

        self.assertEqual(len(result.assertions), 1, "RESOLVED unique pick must emit exactly one assertion")
        actant_roles = {a.role for a in result.assertions[0].actants}
        self.assertIn(ActantRole.SUBJECT, actant_roles)

    def test_unresolved_sentence_is_not_fabricated(self):
        from ah.formalizer.fake_selector import FakeSelector
        from ah.formalizer.runtime_adapter import FormalizerAdapter
        from ah.perception.llm_parser import LLMPerceptionService

        svc = LLMPerceptionService(_StubBackend(), _settings(), formalizer=FormalizerAdapter(FakeSelector.demo("baseline")))
        result = svc.parse("У меня есть книгу.", None)  # S3 baseline -> NO_CANDIDATE: honest, not fabricated
        self.assertEqual(result.assertions, ())

    def test_default_is_legacy_no_formalizer(self):
        from ah.perception.llm_parser import LLMPerceptionService

        svc = LLMPerceptionService(_StubBackend(), _settings())
        self.assertIsNone(svc._formalizer)


class TestBootstrapGate(unittest.TestCase):
    def test_gate_off_by_default(self):
        from ah import bootstrap

        old = os.environ.pop("AH_FORMALIZER", None)
        try:
            self.assertIsNone(bootstrap._build_formalizer_adapter(object()))
        finally:
            if old is not None:
                os.environ["AH_FORMALIZER"] = old

    def test_gate_on_degrades_gracefully_without_llm(self):
        from ah import bootstrap

        old = os.environ.get("AH_FORMALIZER")
        os.environ["AH_FORMALIZER"] = "1"
        try:
            class _Cfg:  # no LLM backend configured -> selector_from_config returns None / raises -> None
                pass

            self.assertIsNone(bootstrap._build_formalizer_adapter(_Cfg()))
        finally:
            if old is None:
                os.environ.pop("AH_FORMALIZER", None)
            else:
                os.environ["AH_FORMALIZER"] = old


if __name__ == "__main__":
    unittest.main()
