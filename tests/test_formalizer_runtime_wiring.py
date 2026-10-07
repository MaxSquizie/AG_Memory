# -*- coding: utf-8 -*-
"""A — Runtime wiring (V7 §14).

The new formalizer vertical is the ONLY runtime perception path: ``orchestrator_base ->
services.perception.parse`` delegates to a :class:`FormalizerAdapter` whenever one is attached, and the
bootstrap builds it unconditionally (no env gate). Proves delegation works and that the removed
``AH_FORMALIZER`` flag no longer has any effect on construction.
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

    def test_service_without_explicit_formalizer_has_none(self):
        from ah.perception.llm_parser import LLMPerceptionService

        svc = LLMPerceptionService(_StubBackend(), _settings())
        self.assertIsNone(svc._formalizer)


class TestBootstrapWiring(unittest.TestCase):
    def test_removed_flag_has_no_effect_on_construction(self):
        """The AH_FORMALIZER gate is gone: setting or unsetting it changes nothing."""
        from ah import bootstrap
        from ah.core.operations import AHCore

        class _Cfg:  # no LLM backend -> selector_from_config yields None / raises -> adapter None
            pass

        core = AHCore()
        old = os.environ.pop("AH_FORMALIZER", None)
        try:
            self.assertIsNone(bootstrap._build_formalizer_adapter(_Cfg(), core))
            os.environ["AH_FORMALIZER"] = "1"  # the flag no longer exists as a gate
            self.assertIsNone(bootstrap._build_formalizer_adapter(_Cfg(), core))
        finally:
            if old is None:
                os.environ.pop("AH_FORMALIZER", None)
            else:
                os.environ["AH_FORMALIZER"] = old


if __name__ == "__main__":
    unittest.main()
