from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings,
    _EVENT_NONE_COMPLETION, _EVENT_RECIPIENT_COMPLETION, _EVENT_SOURCE_COMPLETION,
)
from ah.perception.morphology import MorphInfo

from test_acceptance_regressions_1218 import AcceptanceMorphology

PROJECT = Path(__file__).resolve().parents[1]


class MarginBackend:
    def __init__(self, answers=None):
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
        return LLMResponse(str(item), {})


class OmittedAgentMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        values = {
            "дали": (
                MorphInfo(
                    "дать", "VERB", number="plur", mood="indc",
                    transitivity="tran", grammemes=frozenset({"VERB", "plur", "indc", "tran"}),
                    score=1.0,
                ),
            ),
            "мне": (
                MorphInfo("я", "NPRO", case="datv", number="sing", score=1.0),
            ),
            "книгу": (
                MorphInfo("книга", "NOUN", case="accs", number="sing", score=1.0),
            ),
        }
        return values.get(word.casefold(), super().analyze_all(word))


class TransitiveMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        if word.casefold() in {"читает", "подарил", "взял"}:
            lemma = {"читает": "читать", "подарил": "подарить", "взял": "взять"}[word.casefold()]
            return (
                MorphInfo(
                    lemma, "VERB", mood="indc", number="sing", transitivity="tran",
                    grammemes=frozenset({"VERB", "tran"}), score=1.0,
                ),
            )
        return super().analyze_all(word)


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


class ArchitectureAlignment1231Tests(unittest.TestCase):
    def test_explicit_recipient_stops_hidden_directional_discovery(self):
        backend = MarginBackend()
        result = parser(backend).propose_template_candidate(
            "Иван подарил Марии книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(
            result.candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(backend.calls, [])








if __name__ == "__main__":
    unittest.main()
