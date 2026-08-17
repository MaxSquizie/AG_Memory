from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings,
    _EVENT_RECIPIENT_COMPLETION,
)
from ah.perception.morphology import MorphInfo

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class MarginBackend:
    def __init__(self, answers: dict[str, list[tuple[str, float] | str]]):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov))
        values = self.answers.get(role)
        if not values:
            fallback = legacy_semantic_answer(role, prompt)
            if fallback is not None:
                return LLMResponse(str(fallback), {})
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        item = values.pop(0)
        if isinstance(item, tuple):
            text, margin = item
            return LLMResponse(text, {"choice_margin": margin})
        return LLMResponse(item, {})


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


class NestedMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        values = {
            "сказал": (MorphInfo("сказать", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
            "хочет": (MorphInfo("хотеть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
            "купить": (MorphInfo("купить", "INFN", score=1.0),),
            "билет": (MorphInfo("билет", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
        }
        return values.get(key, super().analyze_all(word))


class SLMContrastive1229Tests(unittest.TestCase):


    def test_cross_clause_content_is_contrastive_and_builds_candidate_ref(self):
        backend = MarginBackend({"perception_frame_relation": [("CONTENT_LINK", 0.80)]})
        result = parser(backend, NestedMorphology()).parse(
            "Иван сказал, что Мария прочитала книгу."
        ).perception
        self.assertEqual(len(result.assertions), 2)
        parent, child = result.assertions
        nested = next(a for a in parent.actants if a.candidate_ref is not None)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        self.assertEqual(nested.candidate_ref, child.local_id)
        roles = [role for role, _prompt, _override in backend.calls]
        self.assertEqual(roles.count("perception_frame_relation"), 1)
        self.assertTrue(all("choice_outputs" not in override for _r, _p, override in backend.calls))

    def test_request_control_uses_contrastive_relation_and_one_direct_controller_choice(self):
        backend = MarginBackend({
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        result = parser(backend, RequestMorphology()).parse(
            "Иван попросил Марию прочитать книгу."
        ).perception
        parent, child = result.assertions
        nested = next(a for a in parent.actants if a.candidate_ref == child.local_id)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        self.assertEqual(child_subject.entity_ref, recipient.entity_ref)
        roles = [role for role, _prompt, _override in backend.calls]
        self.assertEqual(roles.count("perception_frame_relation"), 1)
        self.assertEqual(roles.count("perception_control_subject"), 1)
        self.assertNotIn("perception_content_addressee", roles)

    def test_single_controller_after_want_is_deterministic_after_contrastive_nesting(self):
        backend = MarginBackend({"perception_frame_relation": ["CONTENT_LINK"]})
        result = parser(backend, NestedMorphology()).parse("Мария хочет купить билет.").perception
        parent, child = result.assertions
        nested = next(a for a in parent.actants if a.candidate_ref == child.local_id)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        parent_subject = next(a for a in parent.actants if a.role == ActantRole.SUBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(parent_subject.entity_ref, child_subject.entity_ref)
        roles = [role for role, _prompt, _override in backend.calls]
        self.assertEqual(roles.count("perception_frame_relation"), 1)
        self.assertNotIn("perception_control_subject", roles)


if __name__ == "__main__":
    unittest.main()
