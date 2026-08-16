from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
    _EVENT_NONE_COMPLETION,
)
from ah.perception.morphology import MorphInfo, stable_transitivity

from test_acceptance_regressions_1218 import AcceptanceMorphology
from test_slm_pairwise_1228 import NestedMorphology

PROJECT = Path(__file__).resolve().parents[1]


class RecordingBackend:
    def __init__(self, answers: dict[str, list[tuple[str, float] | str]] | None = None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        item = values.pop(0)
        if isinstance(item, tuple):
            text, margin = item
            return LLMResponse(text, {"choice_margin": margin})
        return LLMResponse(item, {})


class DictionaryMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        special = {
            "спит": (
                MorphInfo(
                    "спать", "VERB", mood="indc", transitivity="intr",
                    grammemes=frozenset({"VERB", "intr"}), score=1.0,
                ),
            ),
            "читает": (
                MorphInfo(
                    "читать", "VERB", mood="indc", transitivity="tran",
                    grammemes=frozenset({"VERB", "tran"}), score=1.0,
                ),
            ),
        }
        return special.get(key, super().analyze_all(word))


def parser(backend, morphology=None):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology or AcceptanceMorphology(),
    )


class ArchitectureAlignment1230Tests(unittest.TestCase):
    def test_material_dictionary_transitivity_requires_agreement(self):
        self.assertEqual(
            stable_transitivity((
                MorphInfo("читать", "VERB", transitivity="tran", score=0.8),
                MorphInfo("читать", "INFN", transitivity="tran", score=0.4),
            )),
            "tran",
        )
        self.assertIsNone(stable_transitivity((
            MorphInfo("x", "VERB", transitivity="tran", score=0.6),
            MorphInfo("x", "VERB", transitivity="intr", score=0.5),
        )))



    def test_binary_frame_relation_uses_exact_generation_not_legacy_margin(self):
        backend = RecordingBackend({
            # A stale scorer margin may still be present in backend metadata, but
            # binary semantic generation is accepted by its exact protocol label.
            "perception_frame_relation": [("CONTENT_LINK", 0.01)],
        })
        result = parser(backend, NestedMorphology()).parse("Мария хочет купить билет.").perception
        parent, child = result.assertions
        nested = next(a for a in parent.actants if a.candidate_ref == child.local_id)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        self.assertEqual(len(backend.calls), 1)
        self.assertNotIn("choice_outputs", backend.calls[0][2])
        self.assertNotIn("decision_margin_threshold", backend.calls[0][2])

    def test_frame_questions_are_relation_specific_not_generic_parent_argument(self):
        content_backend = RecordingBackend({
            "perception_frame_relation": [("CONTENT_LINK", 0.8)],
        })
        parser(content_backend, NestedMorphology()).parse("Иван сказал, что Мария прочитала книгу.")
        self.assertNotIn("choice_outputs", content_backend.calls[0][2])
        self.assertIn("semantic content or selected complement", content_backend.calls[0][1])
        self.assertNotIn("PARENT_ARGUMENT", content_backend.calls[0][1])


if __name__ == "__main__":
    unittest.main()
