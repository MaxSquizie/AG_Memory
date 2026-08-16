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
)

from test_acceptance_regressions_1218 import AcceptanceMorphology

PROJECT = Path(__file__).resolve().parents[1]


class GenerationBackend:
    def __init__(self, answers: str | list[str] | tuple[str, ...]):
        if isinstance(answers, str):
            answers = [answers]
        self.answers = list(answers)
        self.calls: list[tuple[str, str, dict, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov, system))
        if role != "perception_template_hidden_valency":
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        if not self.answers:
            raise AssertionError(f"missing mocked answer for call {len(self.calls)}\n{prompt}")
        return LLMResponse(self.answers.pop(0), {})


def parser(backend: GenerationBackend) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=12, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=AcceptanceMorphology(),
    )


class ArchitectureAlignment1236Tests(unittest.TestCase):






    def test_observed_directional_role_disables_hidden_valency_generation(self):
        backend = GenerationBackend("HAS_SOURCE_SLOT")
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
